"""
HTML email sender via Gmail SMTP + App Password.

No image attachment — the user sees the photo on their iPhone.
The email contains the scene description, story, per-word anchors and cues.

Email setup:
  1. Enable 2-Factor Authentication on the Gmail account
  2. Go to Google Account → Security → App Passwords
  3. Generate an App Password for "Mail" on "Other device"
  4. Set GMAIL_USER and GMAIL_APP_PASSWORD in .env
"""

import html
import logging
import smtplib
from datetime import date
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

from kindle_srs.config import GMAIL_USER, GMAIL_APP_PASSWORD, SEND_TO_EMAIL

logger = logging.getLogger(__name__)


def _photo_block(photo_num: int, description: str, story: str, cards: list[dict]) -> str:
    """Render one photo section as HTML."""
    card_rows = ""
    for c in cards:
        # Everything here is model or user text: escape it before it goes into HTML.
        word = html.escape(c.get("word", ""))
        anchor = html.escape(c.get("visual_anchor", ""))
        cue = html.escape(c.get("memory_cue", ""))
        defn = html.escape(c.get("definition") or c.get("brief_definition") or "")
        card_rows += f"""
        <div style="margin:14px 0; padding:12px 0; border-bottom:1px solid #f0f0f0;">
          <span style="font-size:1.15em; font-weight:bold; color:#b5271e; letter-spacing:0.03em;">
            {word}
          </span>
          <p style="margin:5px 0 3px; color:#444; font-size:0.88em;">
            ↳ <em>{anchor}</em>
          </p>
          {"<p style='margin:3px 0; color:#555; font-size:0.87em;'>" + defn + "</p>" if defn else ""}
          <p style="margin:4px 0 0; color:#999; font-size:0.83em; font-style:italic;">
            💡 {cue}
          </p>
        </div>"""

    description, story = html.escape(description), html.escape(story)
    return f"""
    <div style="border-left:3px solid #b5271e; padding-left:18px; margin:32px 0;">
      <p style="font-size:0.78em; color:#aaa; text-transform:uppercase;
                letter-spacing:1.2px; margin:0 0 8px;">
        Photo {photo_num} &nbsp;·&nbsp; {description}
      </p>
      <p style="font-style:italic; line-height:1.85; color:#333;
                font-size:0.97em; margin:12px 0 20px;">
        {story}
      </p>
      {card_rows}
    </div>"""


def build_html(session_date: str, photo_blocks: list[dict]) -> str:
    """
    Build the full HTML email body.

    photo_blocks: list of dicts, each with:
        description, story, cards (list of card dicts)
    """
    total_words = sum(len(b.get("cards", [])) for b in photo_blocks)
    blocks_html = "".join(
        _photo_block(i + 1, b["description"], b["story"], b["cards"])
        for i, b in enumerate(photo_blocks)
    )

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
</head>
<body style="margin:0; padding:20px; background:#fafafa; font-family:Georgia,serif;">
  <div style="max-width:580px; margin:0 auto; background:#fff;
              padding:28px 32px; border-radius:4px;">

    <h2 style="margin:0 0 4px; font-size:1.3em; color:#222; font-weight:normal;">
      📖 {total_words} new words &nbsp;<span style="color:#bbb;">—</span>&nbsp;
      <span style="font-size:0.9em; color:#888;">{session_date}</span>
    </h2>
    <p style="margin:0 0 8px; font-size:0.82em; color:#bbb;">
      Open the photos on your iPhone as you read each story.
    </p>

    <hr style="border:none; border-top:1px solid #eee; margin:20px 0;">

    {blocks_html}

    <hr style="border:none; border-top:1px solid #eee; margin:32px 0 16px;">
    <p style="font-size:0.75em; color:#ccc; margin:0;">
      KindleSRS · visual memory system
    </p>
  </div>
</body>
</html>"""


def send_email(session_date: str, photo_blocks: list[dict]):
    """
    Send the daily vocabulary email.

    photo_blocks: same format as build_html()
    """
    total_words = sum(len(b.get("cards", [])) for b in photo_blocks)
    subject = f"📖 {total_words} new words — {session_date}"

    html_body = build_html(session_date, photo_blocks)

    msg = MIMEMultipart("alternative")
    msg["Subject"] = subject
    msg["From"] = GMAIL_USER
    msg["To"] = SEND_TO_EMAIL
    msg.attach(MIMEText(html_body, "html", "utf-8"))

    try:
        with smtplib.SMTP_SSL("smtp.gmail.com", 465) as smtp:
            smtp.login(GMAIL_USER, GMAIL_APP_PASSWORD)
            smtp.sendmail(GMAIL_USER, SEND_TO_EMAIL, msg.as_string())
        logger.info(f"Email sent: {subject}")
    except Exception as e:
        logger.error(f"Email failed: {e}")
        raise
