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

## High Level Architecture
          ┌─────────────────────┐
          │    Slack Channel    │
          │ (Monitored Messages)│
          └─────────┬───────────┘
                    │
                    ▼
          ┌─────────────────────┐
          │   Slack API (Async) │
          │  - Fetch messages   │
          │  - Fetch reactions  │
          │  - Get user info    │
          └─────────┬───────────┘
                    │
     ┌──────────────┴───────────────┐
     │    SlackSheetsMonitor Class  │
     │ ──────────────────────────── │
     │  - Filter by trigger emoji   │
     │  - Fetch thread replies      │
     │  - Generate permalinks       │
     │  - Deduplicate messages      │
     │  - Format message metadata   │
     │  - Save state to disk        │
     └──────────────┬───────────────┘
                    │
                    ▼
          ┌──────────────────────┐
          │ Google Sheets API    │
          │ - Auth via service   │
          │   account JSON       │
          │ - Append new rows    │
          └─────────┬────────────┘
                    │
                    ▼
          ┌──────────────────────┐
          │  Google Sheet (Tab)  │
          │  - Logs Slack events │
          └──────────────────────┘


## Logical Components

- Slack API: Fetch messages, user info, reactions, links
- Trigger Filter:	Checks emoji reactions against whitelist
- State Manager:	Tracks which messages have been processed
- Google Sheets API:	Writes structured message data to Sheet2
- Main Monitor Class:	Orchestrates all steps in async fashion


