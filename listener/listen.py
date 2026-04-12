#!/usr/bin/env python3
"""
Real-time Script Listener
Listens to speech, tracks position in script, and forwards commands to interpreters.
NO interpretation logic - just voice recognition and command extraction.
"""

import sys
import argparse
import re
import json
from pathlib import Path
from difflib import SequenceMatcher
import pygame
import vosk
import pyaudio
import threading
import queue
try:
    import websocket
except ImportError:
    websocket = None

DEBUG = False
WEBSOCKET_URL = "ws://localhost:8000/ws"


class WebSocketClient:
    """Simple WebSocket client for forwarding commands."""
    
    def __init__(self, url):
        self.url = url
        self.ws = None
        self.connected = False
        self.message_queue = queue.Queue()
        self.thread = None
        
        if websocket is None:
            print("Warning: websocket-client not installed.")
            return
        
        self.thread = threading.Thread(target=self._run, daemon=True)
        self.thread.start()
    
    def _run(self):
        if websocket is None:
            return
        try:
            self.ws = websocket.WebSocketApp(
                self.url,
                on_open=self._on_open,
                on_error=self._on_error,
                on_close=self._on_close
            )
            self.ws.run_forever()
        except Exception as e:
            print(f"WebSocket error: {e}")
    
    def _on_open(self, ws):
        self.connected = True
        print("Connected to interpreter")
        threading.Thread(target=self._send_messages, daemon=True).start()
    
    def _on_error(self, ws, error):
        print(f"WebSocket error: {error}")
    
    def _on_close(self, ws, close_status_code, close_msg):
        self.connected = False
        print("Disconnected from interpreter")
    
    def _send_messages(self):
        while self.connected:
            try:
                message = self.message_queue.get(timeout=0.1)
                if self.ws and self.connected:
                    self.ws.send(json.dumps(message))
            except queue.Empty:
                continue
            except Exception as e:
                print(f"Error sending message: {e}")
    
    def send_command(self, command_str):
        """Send a raw command string to interpreter."""
        if websocket is None or not self.connected:
            return
        self.message_queue.put({
            "command": "execute",
            "code": command_str
        })
    
    def send_position(self, position, total_words, words, plain_text):
        """Send current position in script to interpreter."""
        if websocket is None or not self.connected:
            return
        self.message_queue.put({
            "command": "update_position",
            "position": position,
            "totalWords": total_words,
            "words": words,
            "plainText": plain_text
        })
    
    def close(self):
        if self.ws:
            self.ws.close()


def parse_script(script_path):
    """
    Parse script file to extract plain text and commands.
    
    Returns:
        (plain_text, commands, script_words)
        - plain_text: Script with commands removed
        - commands: List of (word_index, command_string)
        - script_words: List of words from script
    """
    with open(script_path, 'r', encoding='utf-8') as f:
        content = f.read()
    
    # Find all bracketed commands with their positions
    command_pattern = r'\[([^\]]+)\]'
    matches = list(re.finditer(command_pattern, content))
    
    # Build plain text by removing commands
    plain_text = re.sub(command_pattern, '', content)
    
    # Extract words from plain text
    script_words = re.findall(r'\b\w+\b', plain_text.lower())
    
    # Calculate word index for each command
    commands = []
    for match in matches:
        command_content = match.group(1)
        command_pos = match.start()
        
        # Count how many characters of plain text come before this command
        # We need to subtract the length of all previous commands
        plain_pos = command_pos
        for prev_match in matches:
            if prev_match.start() < command_pos:
                plain_pos -= len(prev_match.group(0))
            else:
                break
        
        # Count words before this position in the plain text
        text_before = plain_text[:plain_pos]
        words_before = re.findall(r'\b\w+\b', text_before.lower())
        word_index = len(words_before)
        
        commands.append((word_index, command_content))
    
    return plain_text, commands, script_words


class RealtimeListener:
    """Listen to speech and forward commands to interpreters."""
    
    def __init__(self, script_path, model_path="./models/vosk"):
        self.script_path = script_path
        
        # Parse script
        self.plain_text, self.commands, self.script_words = parse_script(script_path)
        print(f"Loaded script: {len(self.script_words)} words, {len(self.commands)} commands")
        if DEBUG:
            print(f"Commands: {self.commands}")
        
        # Tracking
        self.recognized_words = []
        self.current_position = 0
        self.executed_commands = set()
        
        # Initialize WebSocket
        self.ws_client = WebSocketClient(WEBSOCKET_URL)
        
        # Initialize Vosk
        self.model = vosk.Model(model_path)
        self.recognizer = vosk.KaldiRecognizer(self.model, 16000)
        self.recognizer.SetWords(True)
        
        # Initialize PyAudio
        self.audio = pyaudio.PyAudio()
        self.stream = None
        
        # Initialize Pygame status window
        pygame.init()
        self.screen = pygame.display.set_mode((800, 200))
        pygame.display.set_caption("Real-time Listener")
        self.font = pygame.font.Font(None, 36)
        self.small_font = pygame.font.Font(None, 24)
    
    def find_position_in_script(self):
        """Find current position in script based on recognized words."""
        if not self.recognized_words:
            return 0
        
        best_match_pos = 0
        best_ratio = 0
        
        # Use sliding window
        window_size = min(10, len(self.recognized_words))
        recent_words = self.recognized_words[-window_size:]
        
        for i in range(len(self.script_words) - len(recent_words) + 1):
            window = self.script_words[i:i + len(recent_words)]
            matcher = SequenceMatcher(None, recent_words, window)
            ratio = matcher.ratio()
            
            if ratio > best_ratio:
                best_ratio = ratio
                best_match_pos = i + len(recent_words)
        
        return best_match_pos
    
    def check_and_execute_commands(self, position):
        """Check if we've reached any commands and execute them."""
        for idx, (command_word_index, command_content) in enumerate(self.commands):
            if idx not in self.executed_commands and position >= command_word_index:
                # Check for meta-command RESET()
                if command_content.strip().upper() == "RESET()":
                    print(f"\n>>> Meta-command RESET() triggered at word {command_word_index}")
                    self.executed_commands.add(idx)
                    self.reset()
                else:
                    print(f"\n>>> Executing command at word {command_word_index}: [{command_content}]")
                    self.ws_client.send_command(command_content)
                    self.executed_commands.add(idx)
    
    def process_audio(self):
        """Process audio from microphone."""
        data = self.stream.read(4000, exception_on_overflow=False)
        
        if self.recognizer.AcceptWaveform(data):
            result = json.loads(self.recognizer.Result())
            text = result.get('text', '')
            
            if text:
                words = re.findall(r'\b\w+\b', text.lower())
                self.recognized_words.extend(words)
                
                print(f"Recognized: {text}")
                if DEBUG:
                    print(f"Total words recognized: {len(self.recognized_words)}")
                
                # Update position
                new_position = self.find_position_in_script()
                if new_position > self.current_position:
                    self.current_position = new_position
                    self.check_and_execute_commands(self.current_position)
                    # Send position update to interpreter
                    self.ws_client.send_position(
                        self.current_position,
                        len(self.script_words),
                        self.script_words,
                        self.plain_text
                    )
    
    def draw_ui(self):
        """Draw status window."""
        self.screen.fill((0, 0, 0))
        
        # Position indicator
        y = 20
        position_text = f"Position: {self.current_position}/{len(self.script_words)}"
        text_surface = self.font.render(position_text, True, (200, 200, 200))
        self.screen.blit(text_surface, (10, y))
        
        # Recent words
        y += 40
        recent = ' '.join(self.recognized_words[-5:])
        heard_text = f"Heard: {recent}"
        text_surface = self.small_font.render(heard_text, True, (100, 200, 100))
        self.screen.blit(text_surface, (10, y))
        
        # Connection status
        y += 40
        status = "Connected" if self.ws_client.connected else "Disconnected"
        color = (100, 255, 100) if self.ws_client.connected else (255, 100, 100)
        status_text = f"Interpreter: {status}"
        text_surface = self.small_font.render(status_text, True, color)
        self.screen.blit(text_surface, (10, y))
        
        # Commands executed
        y += 40
        cmd_text = f"Commands: {len(self.executed_commands)}/{len(self.commands)}"
        text_surface = self.small_font.render(cmd_text, True, (200, 200, 200))
        self.screen.blit(text_surface, (10, y))
        
        pygame.display.flip()
    
    def reset(self):
        """Reset recognition state."""
        print("\n>>> RESET <<<")
        self.recognized_words = []
        self.current_position = 0
        self.executed_commands = set()
        self.recognizer = vosk.KaldiRecognizer(self.model, 16000)
        self.recognizer.SetWords(True)
        
        # Reset browser - clear graphics and reset position
        self.ws_client.send_command("clear()")
        self.ws_client.send_position(
            self.current_position,
            len(self.script_words),
            self.script_words,
            self.plain_text
        )
    
    def run(self):
        """Main loop."""
        # Open audio stream
        self.stream = self.audio.open(
            format=pyaudio.paInt16,
            channels=1,
            rate=16000,
            input=True,
            frames_per_buffer=4000
        )
        
        print("="*60)
        print("REAL-TIME LISTENER")
        print("="*60)
        print(f"Script: {self.script_path}")
        print(f"Words: {len(self.script_words)}")
        print(f"Commands: {len(self.commands)}")
        print("\nControls:")
        print("  R - Reset recognition")
        print("  Q - Quit")
        print("="*60)
        print("\nListening...")
        
        # Send initial position to interpreter
        self.ws_client.send_position(
            self.current_position,
            len(self.script_words),
            self.script_words,
            self.plain_text
        )
        
        running = True
        clock = pygame.time.Clock()
        
        try:
            while running:
                # Handle events
                for event in pygame.event.get():
                    if event.type == pygame.QUIT:
                        running = False
                    elif event.type == pygame.KEYDOWN:
                        if event.key == pygame.K_q:
                            running = False
                        elif event.key == pygame.K_r:
                            self.reset()
                
                # Process audio
                self.process_audio()
                
                # Update UI
                self.draw_ui()
                
                clock.tick(30)
        
        finally:
            self.stream.stop_stream()
            self.stream.close()
            self.audio.terminate()
            self.ws_client.close()
            pygame.quit()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Real-time script listener")
    parser.add_argument("script", help="Path to .script file")
    parser.add_argument("--model", default="./models/vosk", help="Path to Vosk model directory")
    parser.add_argument("--debug", action="store_true", help="Enable debug output")
    
    args = parser.parse_args()
    
    if args.debug:
        DEBUG = True
    
    listener = RealtimeListener(args.script, args.model)
    listener.run()
