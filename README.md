# Slack to Google Sheets Integration

This Python script monitors a Slack channel for specific emoji reactions and logs those messages into a Google Sheet for easy tracking and automation.

## Use Case

Track team activity, workflows, or approvals using simple emoji reactions in Slack — then push those insights into Google Sheets for reporting, audit, or follow-up.

## Features

- Watches for specific emojis representing product areas
- Appends new reactions/messages as rows to a specified Google Sheet
- Supports threading and message context
- Saves state locally to avoid duplicates
- Testable connection to both Slack and Google Sheets APIs
