from agents.extractor import extract_clauses
from agents.risk_flagger import rule_based_flag
from agents.scorer import compute_score

mock_html = """<html><body><main>
<h1>Privacy Policy</h1>
<p>We may share your personal information with our advertising partners and third parties for marketing purposes.
We reserve the right to sell your data to monetize our services.</p>
<p>By using our service, you agree to binding arbitration and waive your right to participate in class action lawsuits.</p>
<p>We automatically renew your subscription and charge your payment method on file unless you cancel before renewal.</p>
<p>We may retain your data indefinitely even after account closure or termination.</p>
<p>We may modify these terms at any time without prior notice. Continued use constitutes acceptance.</p>
<p>We may share your information with law enforcement, government agencies, or intelligence agencies upon request.</p>
<p>We track your location, browsing behavior, and device fingerprint to personalize your experience.</p>
</main></body></html>"""

clauses, quality = extract_clauses(mock_html)
print(f"Extracted {len(clauses)} clauses, quality={quality}")

flags = rule_based_flag(clauses)
print(f"Found {len(flags)} flags:")
for f in flags:
    sev = f["severity"].upper()
    cat = f["category"]
    snip = f["clause_snippet"][:60]
    print(f"  [{sev}] {cat} -- {snip}...")

mock_summaries = [
    {"category": f["category"], "summary": "Risk detected.", "severity": f["severity"]}
    for f in flags
]
score_data = compute_score(mock_summaries)
rating_label = {"green": "[GREEN]", "yellow": "[YELLOW]", "red": "[RED]"}.get(score_data["rating"], "[?]")
print(f"Score: {score_data['score']}/100 -> {rating_label} {score_data['rating'].upper()}")
print("PIPELINE TEST PASSED")
