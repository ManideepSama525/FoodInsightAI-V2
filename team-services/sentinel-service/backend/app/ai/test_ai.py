from predict import predict_attack

samples = [

    "' OR 1=1 --",

    "<script>alert(1)</script>",

    "../../etc/passwd",

    "&& whoami",

    "Hello everyone",

]

for payload in samples:

    result = predict_attack(payload)

    print("=" * 50)
    print("Payload:", payload)
    print("Prediction:", result["prediction"])
    print("Confidence:", result["confidence"], "%")