"""Live end-to-end test — hits the running FastAPI backend with a real policy HTML."""
import urllib.request
import json

payload = json.dumps({
    "url": "https://example.com/privacy",
    "html_text": """<html><body><main>
<h1>Privacy Policy</h1>
<p>We may share your personal information with our advertising partners and third parties for marketing and monetization purposes.
We reserve the right to sell your data to third-party advertisers to monetize our services.</p>

<p>By using our service, you agree to binding arbitration for all disputes and waive your right to participate in class action lawsuits.
All disputes shall be resolved individually and not on a class basis.</p>

<p>We automatically renew your subscription and charge your payment method on file every month unless you cancel before the renewal date.
Cancellation must be made at least 7 days before the renewal date.</p>

<p>We may retain your personal data indefinitely, even after you close or delete your account, as permitted by applicable law.
Data may be stored for as long as it is reasonably necessary for our business purposes.</p>

<p>We may modify these Terms of Service at any time without prior notice to you.
Continued use of our services after any changes constitutes your acceptance of the new terms.</p>

<p>We may share your information with law enforcement agencies, government authorities, or intelligence agencies when required by law
or when we believe it is necessary to protect our rights or the rights of others.</p>

<p>We collect precise geolocation data, track your browsing behavior across websites, monitor your activity and usage patterns,
and create device fingerprints to personalize your experience and serve targeted advertising.</p>

<p>Our services are not directed to children under 13. However, if we discover we have collected data from a child under 13,
we will take steps to delete it. Parental consent may be required for users under 16 in certain jurisdictions.</p>
</main></body></html>"""
}).encode("utf-8")

req = urllib.request.Request(
    "http://localhost:8000/analyze",
    data=payload,
    headers={"Content-Type": "application/json"},
    method="POST"
)

print("Sending request to backend...")
with urllib.request.urlopen(req, timeout=60) as resp:
    result = json.loads(resp.read().decode())

print(f"\nURL: {result['url']}")
print(f"Score: {result['score']}/100")
print(f"Rating: {result['rating'].upper()}")
print(f"Verdict: {result['final_summary']}")
print(f"\nFlags found: {result['flags_found']}")
print(f"Clauses analyzed: {result['clauses_found']}")
print(f"Analysis time: {result['analysis_time_ms']}ms")
print(f"\nBreakdown: {result['breakdown']}")
print("\nSummaries:")
for s in result.get("summaries", []):
    sev = s["severity"].upper()
    print(f"  [{sev}] {s['category']}: {s['summary']}")

print("\nE2E TEST PASSED")
