"""Create the support knowledge base SQLite FTS5 database."""
import sqlite3
import os

db_dir = os.path.dirname(os.path.abspath(__file__))
db_path = os.path.join(db_dir, "support_kb.db")

# Remove existing DB to start fresh
if os.path.exists(db_path):
    os.remove(db_path)

conn = sqlite3.connect(db_path)

conn.execute("""
    CREATE VIRTUAL TABLE support_articles USING fts5(
        title,
        body,
        category,
        tags
    )
""")

articles = [
    ("How to reset your password",
     "To reset your password, go to the login page and click Forgot Password. Enter your email address and you will receive a reset link within 5 minutes. The link expires after 24 hours. If you do not receive the email, check your spam folder or contact support.",
     "account",
     "password reset login authentication"),

    ("Billing FAQ - Payment methods",
     "We accept Visa, Mastercard, American Express, and PayPal. To update your payment method, go to Settings > Billing > Payment Methods. You can add multiple payment methods and set a default. Changes take effect on your next billing cycle.",
     "billing",
     "payment credit card paypal invoice"),

    ("How to cancel your subscription",
     "To cancel your subscription, navigate to Settings > Subscription > Cancel Plan. Your access continues until the end of the current billing period. You can reactivate at any time. Refunds are available within 14 days of the last charge for annual plans.",
     "billing",
     "cancel subscription refund"),

    ("Two-factor authentication setup",
     "Enable two-factor authentication (2FA) for extra security. Go to Settings > Security > Two-Factor Authentication. You can use an authenticator app (recommended) or SMS. Backup codes are generated automatically - store them in a safe place. If you lose access to your 2FA device, use a backup code or contact support for account recovery.",
     "security",
     "2fa mfa security authentication totp"),

    ("API rate limits and throttling",
     "API requests are limited to 1000 requests per minute for standard plans and 5000 for enterprise. When you exceed the limit, you receive a 429 Too Many Requests response with a Retry-After header. Implement exponential backoff in your client. Contact sales for custom rate limits.",
     "api",
     "rate limit throttling 429 api"),

    ("Troubleshooting slow performance",
     "If the application is running slowly: 1) Clear your browser cache and cookies. 2) Disable browser extensions. 3) Check your internet connection speed. 4) Try a different browser. 5) Check our status page at status.example.com for known issues. If the problem persists, collect a HAR file and submit a support ticket.",
     "troubleshooting",
     "slow performance speed latency"),

    ("Data export and GDPR requests",
     "You can export your data at any time from Settings > Privacy > Export Data. The export includes all your content, settings, and activity logs in JSON format. For GDPR deletion requests, submit a ticket through the privacy portal. Deletion is processed within 30 days and is irreversible.",
     "privacy",
     "gdpr export data privacy deletion"),

    ("Integration with Slack",
     "To connect Slack: 1) Go to Settings > Integrations > Slack. 2) Click Connect and authorize the app in your Slack workspace. 3) Choose which channels receive notifications. You can customize notification types (alerts, reports, mentions). Disconnect at any time from the same settings page.",
     "integrations",
     "slack integration notifications webhook"),

    ("Team management and roles",
     "Manage your team from Settings > Team. Available roles: Owner (full access), Admin (manage members and settings), Member (standard access), Viewer (read-only). Owners can transfer ownership. Admins can invite and remove members. SSO is available on enterprise plans.",
     "account",
     "team roles permissions admin sso"),

    ("Troubleshooting webhook delivery failures",
     "If webhooks are not being delivered: 1) Verify the endpoint URL is correct and publicly accessible. 2) Check that your server returns a 2xx status within 30 seconds. 3) Review the webhook delivery log in Settings > Webhooks > Delivery History. Failed deliveries are retried 3 times with exponential backoff. After 3 failures the webhook is disabled - re-enable it manually.",
     "api",
     "webhook delivery failure retry endpoint"),
]

conn.executemany(
    "INSERT INTO support_articles(title, body, category, tags) VALUES (?, ?, ?, ?)",
    articles,
)
conn.commit()

count = conn.execute("SELECT COUNT(*) FROM support_articles").fetchone()[0]
print(f"Created {db_path} with {count} articles")

# Test BM25F query (title=10, body=1, category=5, tags=3)
results = conn.execute(
    """
    SELECT title, -bm25(support_articles, 10.0, 1.0, 5.0, 3.0) AS rank
    FROM support_articles
    WHERE support_articles MATCH ?
    ORDER BY rank DESC
    LIMIT 3
    """,
    ("password",),
).fetchall()

print("Sample BM25F query for 'password':")
for title, rank in results:
    print(f"  {rank:.4f} - {title}")

conn.close()
