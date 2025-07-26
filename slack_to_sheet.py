
"""
Slack to Google Sheets Integration
Monitors Slack for emoji reactions and updates Google Sheets with new rows.
"""

import os
import json
import asyncio
import hashlib
from datetime import datetime, timezone
from typing import List, Dict

# Slack SDK
from slack_sdk.web.async_client import AsyncWebClient
from slack_sdk.errors import SlackApiError

# Google Sheets
from google.oauth2.service_account import Credentials
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError

# Configuration - Your working credentials
TRIGGER_EMOJIS = {"form", "docgen", "relayflag", "box-apps", "box-sign"}
SLACK_BOT_TOKEN = "token"  # Your working token
DEFAULT_CHANNEL_ID = "channel_ID"

# Your Google Sheets Configuration
GOOGLE_CREDENTIALS_PATH = "credentials.json"
SPREADSHEET_ID = "sheet_ID"
SHEET_NAME = "Sheet2"

# State tracking
STATE_FILE = "slack_monitor_state.json"

class SlackSheetsMonitor:
    """Monitors Slack for emoji reactions and updates Google Sheets"""
    
    def __init__(self):
        self.slack_client = AsyncWebClient(token=SLACK_BOT_TOKEN)
        self.sheets_service = None
        self.processed_messages = set()
        
        # Initialize Google Sheets
        self._init_google_sheets()
        
        # Load previous state
        self._load_state()
    
    def _init_google_sheets(self):
        """Initialize Google Sheets API service"""
        try:
            print(f" Loading credentials from: {GOOGLE_CREDENTIALS_PATH}")
            
            if not os.path.exists(GOOGLE_CREDENTIALS_PATH):
                raise FileNotFoundError(f"Credentials file not found: {GOOGLE_CREDENTIALS_PATH}")
            
            credentials = Credentials.from_service_account_file(
                GOOGLE_CREDENTIALS_PATH,
                scopes=['https://www.googleapis.com/auth/spreadsheets']
            )
            
            self.sheets_service = build('sheets', 'v4', credentials=credentials)
            print(" Google Sheets API service initialized")
            
        except Exception as e:
            print(f" Failed to initialize Google Sheets: {e}")
            raise
    
    def _load_state(self):
        """Load previously processed message state"""
        try:
            if os.path.exists(STATE_FILE):
                with open(STATE_FILE, 'r') as f:
                    state = json.load(f)
                    self.processed_messages = set(state.get('processed_messages', []))
                    print(f"📁 Loaded state: {len(self.processed_messages)} processed messages")
            else:
                print("📁 No previous state found, starting fresh")
        except Exception as e:
            print(f" Error loading state: {e}")
            self.processed_messages = set()
    
    def _save_state(self):
        """Save current processing state"""
        try:
            state = {
                'processed_messages': list(self.processed_messages),
                'last_check_time': datetime.now(timezone.utc).isoformat()
            }
            with open(STATE_FILE, 'w') as f:
                json.dump(state, f, indent=2)
        except Exception as e:
            print(f" Error saving state: {e}")
    
    def _get_message_id(self, message: Dict) -> str:
        """Generate unique ID for a message"""
        unique_string = f"{message.get('ts', '')}-{message.get('user', '')}-{message.get('text', '')[:50]}"
        return hashlib.md5(unique_string.encode()).hexdigest()
    
    async def test_connections(self) -> bool:
        """Test both Slack and Google Sheets connections"""
        print("🔍 Testing connections...")
        
        # Test Slack
        try:
            response = await self.slack_client.auth_test()
            if response["ok"]:
                user = response.get("user", "Unknown")
                team = response.get("team", "Unknown")
                print(f" Slack connected as: {user} in {team}")
            else:
                print(f" Slack auth failed: {response.get('error')}")
                return False
        except Exception as e:
            print(f" Slack connection error: {e}")
            return False
        
        # Test Google Sheets
        try:
            result = self.sheets_service.spreadsheets().get(
                spreadsheetId=SPREADSHEET_ID
            ).execute()
            
            title = result.get('properties', {}).get('title', 'Unknown')
            print(f" Google Sheets connected: '{title}'")
            return True
            
        except HttpError as e:
            print(f" Google Sheets API error: {e}")
            return False
        except Exception as e:
            print(f" Google Sheets connection error: {e}")
            return False
    
    async def get_user_name(self, user_id: str) -> str:
        """Get user's display name"""
        try:
            result = await self.slack_client.users_info(user=user_id)
            if result["ok"]:
                user = result["user"]
                return user.get("display_name") or user.get("real_name") or user.get("name", user_id)
            return user_id
        except:
            return user_id
    
    async def get_channel_name(self, channel_id: str) -> str:
        """Get channel's display name"""
        try:
            result = await self.slack_client.conversations_info(channel=channel_id)
            if result["ok"]:
                channel = result["channel"]
                return f"#{channel.get('name', channel_id)}"
            return channel_id
        except:
            return channel_id
    
    async def get_permalink(self, channel_id: str, message_ts: str) -> str:
        """Get permalink for a message"""
        try:
            result = await self.slack_client.chat_getPermalink(
                channel=channel_id,
                message_ts=message_ts
            )
            
            if result["ok"]:
                return result.get("permalink", "")
            else:
                return ""
        except:
            return ""
    
    async def get_thread_replies(self, channel_id: str, thread_ts: str) -> List[Dict]:
        """Fetch all replies in a thread"""
        try:
            result = await self.slack_client.conversations_replies(
                channel=channel_id,
                ts=thread_ts
            )
            
            if result["ok"]:
                return result.get("messages", [])
            else:
                return []
        except:
            return []
    
    def has_trigger_emoji(self, message: Dict) -> List[str]:
        """Check if message has trigger emoji reactions"""
        reactions = message.get("reactions", [])
        trigger_emojis_found = []
        
        for reaction in reactions:
            emoji_name = reaction.get("name", "")
            if emoji_name in TRIGGER_EMOJIS:
                trigger_emojis_found.append(emoji_name)
        
        return trigger_emojis_found
    
    async def fetch_new_triggered_messages(self, channel_id: str) -> List[Dict]:
        """Fetch only new triggered messages that haven't been processed"""
        try:
            print(f"🔍 Checking for new triggered messages in {channel_id}...")
            
            # Get recent messages
            result = await self.slack_client.conversations_history(
                channel=channel_id, 
                limit=100
            )
            
            if not result["ok"]:
                print(f" Error fetching channel history: {result.get('error')}")
                return []
            
            messages = result.get("messages", [])
            new_triggered_messages = []
            
            # Get channel name once for all messages
            channel_name = await self.get_channel_name(channel_id)
            
            for message in messages:
                # Generate message ID
                message_id = self._get_message_id(message)
                
                # Skip if already processed
                if message_id in self.processed_messages:
                    continue
                
                # Check for trigger emojis
                trigger_emojis = self.has_trigger_emoji(message)
                
                if trigger_emojis:
                    print(f" Found NEW triggered message with emojis: {trigger_emojis}")
                    
                    # Get user name
                    user_id = message.get("user", "Unknown")
                    user_name = await self.get_user_name(user_id)
                    
                    # Get permalink
                    permalink = await self.get_permalink(channel_id, message.get("ts", ""))
                    
                    # Handle threading
                    parent_text = ""
                    thread_replies = []
                    
                    if message.get("thread_ts"):
                        thread_messages = await self.get_thread_replies(channel_id, message["thread_ts"])
                        
                        if thread_messages:
                            parent_text = thread_messages[0].get("text", "")
                            thread_replies = [
                                msg.get("text", "") for msg in thread_messages[1:]
                                if msg.get("ts") != message.get("ts")
                            ]
                    
                    # Format timestamp
                    timestamp = message.get("ts", "")
                    if timestamp:
                        try:
                            dt = datetime.fromtimestamp(float(timestamp), tz=timezone.utc)
                            formatted_timestamp = dt.strftime("%Y-%m-%d %H:%M:%S UTC")
                        except:
                            formatted_timestamp = timestamp
                    else:
                        formatted_timestamp = "Unknown"
                    
                    new_triggered_messages.append({
                        "id": message_id,
                        "timestamp": formatted_timestamp,
                        "user": user_name,
                        "channel": channel_name,  # Using channel name instead of ID
                        "reacted_message_text": message.get("text", ""),
                        "parent_message": parent_text,
                        "thread_replies": "\n".join(thread_replies),
                        "link": permalink,
                        "trigger_emojis": ", ".join(trigger_emojis)
                    })
                    
                    # Mark as processed
                    self.processed_messages.add(message_id)
            
            print(f" Found {len(new_triggered_messages)} NEW triggered messages")
            return new_triggered_messages
            
        except SlackApiError as e:
            print(f" Slack API error: {e.response['error']}")
            return []
        except Exception as e:
            print(f" Error fetching messages: {e}")
            return []
    
    def append_to_sheet(self, data: List[Dict]) -> bool:
        """Append new rows to Google Sheets"""
        if not data:
            print("📭 No new data to append")
            return True
        
        try:
            print(f"📊 Appending {len(data)} new rows to Google Sheets...")
            
            # Prepare rows for appending
            rows = []
            for item in data:
                row = [
                    item.get("timestamp", ""),
                    item.get("user", ""),
                    item.get("channel", ""),
                    item.get("reacted_message_text", ""),
                    item.get("parent_message", ""),
                    item.get("thread_replies", ""),
                    item.get("link", ""),
                    item.get("trigger_emojis", "")
                ]
                rows.append(row)
            
            # Check if sheet has headers
            try:
                sheet_values = self.sheets_service.spreadsheets().values().get(
                    spreadsheetId=SPREADSHEET_ID,
                    range=f"{SHEET_NAME}!A1:H1"
                ).execute()
                
                values = sheet_values.get('values', [])
                
                if not values:
                    # Sheet is empty, add headers first
                    headers = [
                        "Timestamp", "User", "Channel", "Reacted Message Text",
                        "Parent Message", "Thread Replies", "Link", "Trigger Emojis"
                    ]
                    
                    self.sheets_service.spreadsheets().values().append(
                        spreadsheetId=SPREADSHEET_ID,
                        range=f"{SHEET_NAME}!A1",
                        valueInputOption='RAW',
                        insertDataOption='INSERT_ROWS',
                        body={'values': [headers]}
                    ).execute()
                    
                    print("📋 Added headers to sheet")
                        
            except HttpError:
                # Sheet doesn't exist, will be created automatically
                pass
            
            # Append the data rows
            result = self.sheets_service.spreadsheets().values().append(
                spreadsheetId=SPREADSHEET_ID,
                range=f"{SHEET_NAME}!A:H",
                valueInputOption='RAW',
                insertDataOption='INSERT_ROWS',
                body={'values': rows}
            ).execute()
            
            updated_cells = result.get('updates', {}).get('updatedCells', 0)
            print(f"Appended {len(data)} rows ({updated_cells} cells) to Google Sheets")
            return True
            
        except HttpError as e:
            print(f"Google Sheets API error: {e}")
            return False
        except Exception as e:
            print(f"Error appending to sheets: {e}")
            return False
    
    async def run_monitor_cycle(self) -> int:
        """Run one monitoring cycle"""
        try:
            # Fetch new triggered messages
            new_messages = await self.fetch_new_triggered_messages(DEFAULT_CHANNEL_ID)
            
            if new_messages:
                # Append to Google Sheets
                success = self.append_to_sheet(new_messages)
                
                if success:
                    # Save state
                    self._save_state()
                    print(f" Successfully processed {len(new_messages)} new messages")
                    return len(new_messages)
                else:
                    print(" Failed to update Google Sheets")
                    return 0
            else:
                print("📭 No new triggered messages found")
                return 0
                
        except Exception as e:
            print(f" Error in monitor cycle: {e}")
            return 0

async def main():
    """Main function"""
    print("Slack to Google Sheets Monitor (FINAL WORKING VERSION)")
    print("=" * 70)
    
    print(f" Trigger emojis: {', '.join([f':{e}:' for e in TRIGGER_EMOJIS])}")
    print(f" Target channel: {DEFAULT_CHANNEL_ID}")
    print(f" Target sheet: {SHEET_NAME}")
    print(f" Using working token: {SLACK_BOT_TOKEN[:20]}...{SLACK_BOT_TOKEN[-10:]}")
    
    try:
        # Initialize monitor
        monitor = SlackSheetsMonitor()
        
        # Test connections
        if not await monitor.test_connections():
            print(" Connection tests failed")
            return
        
        # Run one cycle first
        print("\n🔄 Running initial check...")
        new_count = await monitor.run_monitor_cycle()
        
        if new_count > 0:
            print(f" Initial run processed {new_count} messages")
        else:
            print("📭 No new emoji-triggered messages found in recent history")
        
        print(f"\nIntegration test complete!")
        print(f" Check your Google Sheet: https://docs.google.com/spreadsheets/d/{SPREADSHEET_ID}")
        
        print(f"\n To run continuous monitoring:")
        print(f"   python slack_to_sheets_final.py")
        
    except Exception as e:
        print(f" Error: {e}")

if __name__ == "__main__":
    asyncio.run(main()) 
