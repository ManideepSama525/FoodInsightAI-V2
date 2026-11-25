MITRE_ATTACKS = {

    "SQL Injection": {
        "technique": "Exploit Public-Facing Application",
        "id": "T1190",
        "tactic": "Initial Access",
    },

    "Cross Site Scripting": {
        "technique": "Exploit Public-Facing Application",
        "id": "T1190",
        "tactic": "Initial Access",
    },

    "Directory Traversal": {
        "technique": "File and Directory Discovery",
        "id": "T1083",
        "tactic": "Discovery",
    },

    "Command Injection": {
        "technique": "Command and Scripting Interpreter",
        "id": "T1059",
        "tactic": "Execution",
    },

    "Brute Force": {
        "technique": "Brute Force",
        "id": "T1110",
        "tactic": "Credential Access",
    },

}


def get_mitre_mapping(attack: str):

    return MITRE_ATTACKS.get(
        attack,
        {
            "technique": "Unknown",
            "id": "-",
            "tactic": "-",
        },
    )