"""One-time Yahoo sign-in for the lineup bot. Kyle runs this once on his PC.

It asks for the Yahoo app's Client ID and Client Secret, opens Yahoo's
approval page, takes the code Yahoo shows, and stores all three values as
hidden GitHub secrets on kyeill/yahoo-lineup. Nothing is printed or saved
to disk, so the values never leave this terminal except into GitHub.
"""
import base64
import getpass
import json
import subprocess
import sys
import urllib.error
import urllib.parse
import urllib.request
import webbrowser

REPO = "kyeill/yahoo-lineup"
REDIRECT_URI = "oob"  # must match lineup.py


def main():
    print("Paste the Client ID from your Yahoo app page, then press Enter.")
    cid = input("Client ID: ").strip()
    print("Now the Client Secret. It will NOT show as you paste it - that's normal.")
    secret = getpass.getpass("Client Secret: ").strip()

    url = "https://api.login.yahoo.com/oauth2/request_auth?" + urllib.parse.urlencode({
        "client_id": cid, "redirect_uri": REDIRECT_URI,
        "response_type": "code", "language": "en-us"})
    print("\nOpening Yahoo in your browser. Click 'Agree' / 'Allow'.")
    print("Yahoo will then show a short code. Copy it and paste it here.")
    webbrowser.open(url)
    code = input("Code: ").strip()

    body = urllib.parse.urlencode({
        "grant_type": "authorization_code", "code": code,
        "redirect_uri": REDIRECT_URI}).encode()
    basic = base64.b64encode(f"{cid}:{secret}".encode()).decode()
    req = urllib.request.Request(
        "https://api.login.yahoo.com/oauth2/get_token", body,
        {"Authorization": f"Basic {basic}",
         "Content-Type": "application/x-www-form-urlencoded"})
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            refresh = json.load(r)["refresh_token"]
    except urllib.error.HTTPError as e:
        sys.exit(f"\nYahoo refused the code ({e.code}): {e.read()[:300]!r}\n"
                 "Nothing was saved. Copy this whole message back to Claude.")

    for name, value in [("YAHOO_CLIENT_ID", cid),
                        ("YAHOO_CLIENT_SECRET", secret),
                        ("YAHOO_REFRESH_TOKEN", refresh)]:
        subprocess.run(["gh", "secret", "set", name, "-R", REPO],
                       input=value, text=True, check=True)
    print("\nDone - all three secrets are stored on GitHub. Tell Claude it worked.")


if __name__ == "__main__":
    main()
