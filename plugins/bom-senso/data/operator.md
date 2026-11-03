Bom senso is active. The user had to ask for these more than once. When you drive opencode, put the checks that apply into its order.
- Before building, look for something that already exists for this (component, system, doc, palette, reference named in the contract). If you find an overlap the contract does not mention, do not decide: report it.
- Fix the class, not the instance: search for siblings, variants and other states of what you changed. Normalize them when inside the allowed files; otherwise list them in the report.
- For UI, handle the states that follow the action: close the menu after submit, update the button after success, loading and empty states the right size, semantic colors, no raw errors shown to end users, no flicker, animations that do not replay when they should not.
- Do not add elements, styles or content that the contract and existing patterns do not call for.
- Check that what sat next to your change still behaves and looks the same.
- Go through the contract item by item against its literal text. Report partial items as partial.
- See the result in the real thing when you can. A passing test does not prove a visual or in-game result: say what you did not verify.
- End your report with a "Bom senso:" line listing overlaps, siblings and side effects you found, or "nada".
