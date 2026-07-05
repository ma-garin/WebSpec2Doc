# Getting Started with WebSpec2Doc — A Plain-Language Guide

This guide is written for everyone, including people who do not write code. It avoids technical jargon as much as possible.

---

## What does this tool do?

**Give it the URL of a live website, and it automatically creates a "manual" for that site and a "first draft of tests" for it.**

It is helpful in situations like these:

- "This web system was built long ago, but no documentation remains. Nobody knows what screens exist."
- "I just took over this project and I don't know what to test first."
- "We renewed the site and want to check that the screens still work the same way."

When you provide a URL, WebSpec2Doc visits the site automatically and produces a bundled report containing:

1. **What screens exist** (a list, with a description of each screen)
2. **What you can enter or do on each screen** (input fields, buttons, required items)
3. **What should be tested** (test viewpoints and draft test cases)
4. **Screenshots of the screens** (real images, as evidence)

---

## Three things that make it nice

| Strength | What it means |
|---|---|
| **Based on the real thing** | It does not guess. It records only what it actually confirmed by operating the site. You can trust it. |
| **Start even without documents** | Even with no design documents on hand, a URL is enough to capture the site's current state as a document. |
| **Notice what changed** | It compares the previous run with the current one and finds "what changed" automatically — useful for renewals and for spotting defects. |

---

## How to use it (4 steps)

Just follow the on-screen instructions.

1. **Enter a URL** — Type the address (URL) of the site you want to inspect and press "Analyze". It automatically discovers how many screens there are.
2. **Choose conditions** — Select which screens to inspect in detail. If the site needs a login, a form for ID and password appears automatically.
3. **Run it** — The analysis starts. You can see which screen it is looking at in real time. Just wait.
4. **View the results** — Check the finished report in the on-screen tabs. You can also save it as Excel, PDF, or images.

> Any password you enter for login is used only for that analysis and is **not saved**. It is safe to use.

---

## Frequently Asked Questions (FAQ)

**Q. Do I need programming knowledge?**
No. You only enter a URL and press a button.

**Q. Can it inspect sites that require sign-in or login?**
Yes. If you enter an ID and password, it will inspect the screens shown after logging in. The password is not saved.

**Q. Is the data of the inspected site sent anywhere outside?**
No. It can run entirely inside your internal network, without sending data outside.

**Q. In what formats can I receive the results?**
Besides the on-screen report, you can save it as Excel, PDF, images, and Markdown, so it fits straight into your existing documentation.

**Q. I want to see the difference before and after a renewal.**
There is an "old vs. new comparison" feature. Give it the URLs of the old and new versions, and it highlights the screens that changed or broke, color-coded.

**Q. What if the analysis does not work?**
Most problems come from an incomplete setup. Ask a developer to run the "environment doctor" (`make doctor`), which shows the cause and how to fix it.

---

## Want to know more?

- Step-by-step usage (a bit more detailed): [userguide.md](userguide.md)
- For those handling development and deployment: [DEVELOPMENT.md](DEVELOPMENT.md)
- 日本語版: [GUIDE_ja.md](GUIDE_ja.md)
