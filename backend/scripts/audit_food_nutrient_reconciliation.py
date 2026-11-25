from __future__ import annotations
import json
from collections import Counter
from pathlib import Path
from neo4j import GraphDatabase
from sqlalchemy import select
from backend.app.core.config import get_settings
from backend.app.db.session import SessionLocal
from backend.app.models.food import Food, FoodNutrient

FIELDS = ("amount", "unit", "basis_g", "source", "source_nutrient_id")

def num(v):
    return None if v is None else float(v)

def equal(field, a, b):
    if field in ("amount", "basis_g"):
        if a is None or b is None:
            return a is b
        return abs(float(a) - float(b)) <= 1e-9
    return a == b

def main():
    settings = get_settings()
    if not settings.knowledge_graph_enabled or not settings.neo4j_password:
        raise RuntimeError("Knowledge graph disabled or Neo4j credentials missing")

    db = SessionLocal()
    driver = None
    try:
        foods = db.scalars(select(Food)).all()
        food_names = {x.id: x.name for x in foods}
        rows = db.scalars(
            select(FoodNutrient).where(FoodNutrient.amount.is_not(None))
        ).all()
        sql = {}
        sql_counts = Counter()
        for x in rows:
            pair = (x.food_id, x.nutrient_key)
            sql_counts[pair] += 1
            sql.setdefault(pair, {
                "amount": num(x.amount), "unit": x.unit, "basis_g": num(x.basis_g),
                "source": x.source, "source_nutrient_id": x.source_nutrient_id
            })
        sql_dupes = [
            {"food_id": k[0], "key": k[1], "count": n}
            for k, n in sql_counts.items() if n > 1
        ]

        driver = GraphDatabase.driver(
            settings.neo4j_uri,
            auth=(settings.neo4j_username, settings.neo4j_password),
            connection_timeout=5,
        )
        driver.verify_connectivity()
        with driver.session(database=settings.neo4j_database) as s:
            records = list(s.run("""
                MATCH (f:Food)-[r:HAS_NUTRIENT]->(n:Nutrient)
                RETURN f.food_id AS food_id, n.key AS key, count(r) AS rel_count,
                       collect({amount:r.amount, unit:r.unit, basis_g:r.basis_g,
                                source:r.source, source_nutrient_id:r.source_nutrient_id}) AS props
            """))

        neo = {}
        neo_dupes = []
        neo_total = 0
        for rec in records:
            pair = (rec["food_id"], rec["key"])
            count = int(rec["rel_count"])
            neo_total += count
            if count > 1:
                neo_dupes.append({"food_id": pair[0], "key": pair[1], "count": count})
            if rec["props"]:
                neo[pair] = rec["props"][0]

        missing = sorted(set(sql) - set(neo), key=lambda x: (str(x[0]), str(x[1])))
        extra = sorted(set(neo) - set(sql), key=lambda x: (str(x[0]), str(x[1])))
        diffs = []
        for pair in sorted(set(sql) & set(neo), key=lambda x: (str(x[0]), str(x[1]))):
            changes = {}
            for field in FIELDS:
                if not equal(field, sql[pair].get(field), neo[pair].get(field)):
                    changes[field] = {"sql": sql[pair].get(field), "neo4j": neo[pair].get(field)}
            if changes:
                diffs.append({
                    "food_id": pair[0], "food_name": food_names.get(pair[0]),
                    "nutrient_key": pair[1], "differences": changes
                })

        report = {
            "read_only": True,
            "sql": {"foods": len(foods), "nutrient_rows": len(rows),
                    "unique_pairs": len(sql), "duplicate_pairs": sql_dupes},
            "neo4j": {"relationships": neo_total, "unique_pairs": len(neo),
                      "duplicate_pairs": neo_dupes},
            "comparison": {
                "missing_in_neo4j": [
                    {"food_id": f, "food_name": food_names.get(f), "key": k} for f, k in missing
                ],
                "extra_in_neo4j": [
                    {"food_id": f, "food_name": food_names.get(f), "key": k} for f, k in extra
                ],
                "property_differences": diffs
            }
        }
        clean = not (missing or extra or diffs or neo_dupes or sql_dupes)
        report["result"] = "MATCH" if clean else "DIFFERENCES_FOUND"
        out = Path("/app/storage/food_nutrient_reconciliation_audit.json")
        out.write_text(json.dumps(report, indent=2, ensure_ascii=False, default=str), encoding="utf-8")

        print("=" * 68)
        print("FOODINSIGHTAI SQL / NEO4J NUTRIENT RECONCILIATION — READ ONLY")
        print(f"SQL foods:                         {len(foods)}")
        print(f"SQL nutrient rows:                 {len(rows)}")
        print(f"SQL unique pairs:                  {len(sql)}")
        print(f"Neo4j relationships:               {neo_total}")
        print(f"Neo4j unique pairs:                 {len(neo)}")
        print(f"SQL duplicate pairs:               {len(sql_dupes)}")
        print(f"Neo4j duplicate pairs:             {len(neo_dupes)}")
        print(f"Missing in Neo4j:                  {len(missing)}")
        print(f"Extra in Neo4j:                    {len(extra)}")
        print(f"Property difference pairs:         {len(diffs)}")
        print(f"RESULT: {report['result']}")
        print(f"JSON report: {out}")
        for label, data in (
            ("MISSING IN NEO4J", report["comparison"]["missing_in_neo4j"]),
            ("EXTRA IN NEO4J", report["comparison"]["extra_in_neo4j"]),
            ("PROPERTY DIFFERENCES", diffs),
        ):
            if data:
                print(f"\\n{label} (first 30):")
                print(json.dumps(data[:30], indent=2, default=str))
        print("=" * 68)
        return 0 if clean else 2
    finally:
        if driver:
            driver.close()
        db.close()

if __name__ == "__main__":
    raise SystemExit(main())
