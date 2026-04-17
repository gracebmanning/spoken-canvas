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
import threading
import queue
try:
    import websocket
except ImportError:
    websocket = None

DEBUG = False
WEBSOCKET_URL = "ws://localhost:8000/ws"


def normalize_text_for_matching(text):
    """
    Normalize text for fuzzy matching by removing punctuation and 
    standardizing spacing. This handles differences like:
    - "real-time" vs "real time"
    - "it's" vs "its"
    - Extra spaces, tabs, newlines

    Returns:
        List of normalized words (lowercase, no punctuation)
    """
    if not text:
        return []

    # Convert to lowercase
    text = text.lower()

    # Replace common punctuation with spaces to separate words
    # This handles hyphenated words, contractions, etc.
    for char in "-–—_/':":
        text = text.replace(char, ' ')

    # Remove all other punctuation and special characters
    # Keep only letters, numbers, and spaces
    text = re.sub(r'[^\w\s]', '', text)

    # Split into words and filter out empty strings
    words = [w for w in text.split() if w]

    return words


def create_recognizer(recognizer_type, model_path=None, sample_rate=16000):
    """
    Factory function to create a speech recognizer based on type.

    Args:
        recognizer_type: "vosk" or "whisper"
        model_path: Path to the model (optional - uses defaults if None)
        sample_rate: Audio sample rate

    Returns:
        Instance of a speech recognizer

    Raises:
        ImportError: If the required recognizer dependencies are not installed
        ValueError: If recognizer_type is not supported
    """
    if recognizer_type == "vosk":
        try:
            from recognizers import VoskRecognizer
            # model_path is optional for Vosk, it auto-detects
            return VoskRecognizer(model_path=model_path, sample_rate=sample_rate)
        except ImportError as e:
            print(f"Error: Vosk recognizer dependencies not installed.")
            print(f"Install with: pip install vosk pyaudio")
            raise

    elif recognizer_type == "whisper":
        try:
            from recognizers import WhisperRecognizer
            # For Whisper, model_path is the model name (e.g., "base")
            model_name = model_path if model_path else "base"
            # Use English by default for more reliable recognition
            return WhisperRecognizer(model_name=model_name, sample_rate=sample_rate, language="en")
        except ImportError as e:
            error_msg = str(e)
            if "WhisperRecognizer" in error_msg or "whisper" in error_msg.lower():
                print(f"Error: Whisper recognizer dependencies not installed.")
                print(f"To use Whisper, install dependencies:")
                print(f"  pip install openai-whisper numpy")
                print(f"\nNote: Whisper also requires ffmpeg for audio processing.")
                print(f"Falling back to Vosk is recommended (use --recognizer vosk)")
            raise

    else:
        raise ValueError(f"Unsupported recognizer type: {recognizer_type}. Choose 'vosk' or 'whisper'")


class WebSocketClient:
    """Simple WebSocket client for forwarding commands."""

    def __init__(self, url):
        self.url = url
        self.ws = None
        self.connected = False
        self.message_queue = queue.Queue()
        self.thread = None
        self.should_reconnect = True

        if websocket is None:
            print("Warning: websocket-client not installed.")
            return

        self.thread = threading.Thread(target=self._run, daemon=True)
        self.thread.start()

    def _run(self):
        if websocket is None:
            return

        reconnect_delay = 2  # seconds

        while self.should_reconnect:
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

            # If connection closed and we should reconnect, wait and retry
            if self.should_reconnect and not self.connected:
                print(f"Reconnecting in {reconnect_delay} seconds...")
                import time
                time.sleep(reconnect_delay)

    def _on_open(self, ws):
        self.connected = True
        print("Connected to interpreter")
        threading.Thread(target=self._send_messages, daemon=True).start()

    def _on_error(self, ws, error):
        # Only print if it's not just a connection error
        if "Connection refused" not in str(error):
            print(f"WebSocket error: {error}")

    def _on_close(self, ws, close_status_code, close_msg):
        self.connected = False
        print("Disconnected from interpreter (listener continues working)")
        print("  Tip: Make sure 'python listener/serve.py' is running")

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

    def send_command(self, command_str, target="browser"):
        """Send a raw command string to interpreter."""
        if websocket is None or not self.connected:
            return
        self.message_queue.put({
            "target": target,
            "command": "execute",
            "code": command_str
        })

    def send_position(self, position, total_words, words, plain_text, target="browser"):
        """
        Send current position in script to interpreter.

        Args:
            target: Destination interpreter ("browser", "td", etc.)
        """
        if websocket is None or not self.connected:
            return
        self.message_queue.put({
            "target": target,
            "command": "update_position",
            "position": position,
            "totalWords": total_words,
            "words": words,
            "plainText": plain_text
        })

    def close(self):
        self.should_reconnect = False
        if self.ws:
            self.ws.close()


def parse_script(script_path):
    """
    Parse script file to extract plain text, commands, and sentences.

    Returns:
        (plain_text, commands, script_words, sentences)
        - plain_text: Script with commands removed
        - commands: List of (word_index, command_string)
        - script_words: List of normalized words from script (for matching)
        - sentences: List of (start_word_idx, end_word_idx, sentence_text) tuples
    """
    with open(script_path, 'r', encoding='utf-8') as f:
        content = f.read()

    # Find all bracketed commands with their positions
    command_pattern = r'\[([^\]]+)\]'
    matches = list(re.finditer(command_pattern, content))

    # Build plain text by removing commands
    plain_text = re.sub(command_pattern, '', content)

    # Normalize and extract words for matching
    script_words = normalize_text_for_matching(plain_text)

    # Break into sentences - split on periods, newlines, or command boundaries
    # Commands act as natural sentence breaks
    sentences = []
    current_sentence_start = 0
    current_text = []

    # Split plain text by sentence boundaries (period, double newline, or end of text)
    sentence_parts = re.split(r'\.(?:\s+|\n+)|(?:\n\s*\n)', plain_text)

    for part in sentence_parts:
        if not part.strip():
            continue

        # Get normalized words for this sentence part
        part_words = normalize_text_for_matching(part)
        if not part_words:
            continue

        # Add sentence
        sentence_end = current_sentence_start + len(part_words)
        sentences.append((
            current_sentence_start,
            sentence_end,
            ' '.join(part_words)
        ))
        current_sentence_start = sentence_end

    # If no sentences found, treat whole script as one sentence
    if not sentences and script_words:
        sentences.append((0, len(script_words), ' '.join(script_words)))

    # Calculate word index for each command (based on normalized words)
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

        # Count normalized words before this position
        text_before = plain_text[:plain_pos]
        words_before = normalize_text_for_matching(text_before)
        word_index = len(words_before)

        commands.append((word_index, command_content))

    return plain_text, commands, script_words, sentences


class RealtimeListener:
    """Listen to speech and forward commands to interpreters."""

    def __init__(self, script_path, recognizer_type="vosk", model_path=None):
        self.script_path = script_path

        # Parse script
        self.plain_text, self.commands, self.script_words, self.sentences = parse_script(script_path)
        print(
            f"Loaded script: {len(self.script_words)} words, {len(self.commands)} commands, {len(self.sentences)} sentences")
        if DEBUG:
            print(f"Commands: {self.commands}")
            print(f"Sentences: {[(s[0], s[1]) for s in self.sentences]}")  # Just show word ranges

        # Tracking - now sentence-based
        self.recognized_words = []
        self.current_position = 0
        self.current_sentence_idx = 0  # Which sentence we're waiting for
        self.accumulated_words = []  # Accumulate words until we match a sentence
        self.executed_commands = set()

        # Initialize WebSocket
        self.ws_client = WebSocketClient(WEBSOCKET_URL)

        # Initialize speech recognizer (dynamically based on type)
        print(f"Initializing {recognizer_type} recognizer...")
        self.recognizer = create_recognizer(recognizer_type, model_path, sample_rate=16000)

        # Initialize Pygame status window
        pygame.init()
        self.screen = pygame.display.set_mode((900, 230))
        pygame.display.set_caption("Real-time Listener")
        self.font = pygame.font.Font(None, 36)
        self.small_font = pygame.font.Font(None, 24)

    def find_position_in_script(self):
        """
        Sentence-level matching: accumulate words until they match the next expected sentence.
        Returns the new position if a sentence match is found, otherwise current position.
        """
        if self.current_sentence_idx >= len(self.sentences):
            # We're at the end of the script
            return self.current_position

        # Get the next expected sentence
        sentence_start, sentence_end, expected_text = self.sentences[self.current_sentence_idx]
        expected_words = expected_text.split()

        # Get accumulated words as a single string
        accumulated_text = ' '.join(self.accumulated_words)

        # Need at least some words to attempt a match
        if len(self.accumulated_words) < 3:
            return self.current_position

        # Try to match accumulated words against expected sentence
        matcher = SequenceMatcher(None, self.accumulated_words, expected_words)
        ratio = matcher.ratio()

        if DEBUG:
            print(f"\n  Sentence matching:")
            print(f"    Expected ({len(expected_words)} words): {expected_text[:60]}...")
            print(f"    Accumulated ({len(self.accumulated_words)} words): {accumulated_text[:60]}...")
            print(f"    Similarity: {ratio:.2f}")

        # High threshold for sentence matching - must be very close
        # This prevents advancing on partial matches or wrong content
        threshold = 0.70

        # Also require that we have accumulated enough words (at least 70% of expected sentence length)
        min_length_ratio = 0.70
        length_ratio = len(self.accumulated_words) / len(expected_words) if expected_words else 0

        if ratio >= threshold and length_ratio >= min_length_ratio:
            # Match found! Advance to end of this sentence
            print(f"✓ Sentence match! Advancing from word {self.current_position} to {sentence_end}")
            self.current_sentence_idx += 1
            self.accumulated_words.clear()  # Clear buffer for next sentence
            return sentence_end

        # Not enough match yet - keep accumulating
        # But if we've accumulated way more words than expected, something's wrong
        if len(self.accumulated_words) > len(expected_words) * 1.5:
            # We've said too much without matching - likely user went off-script
            # Clear and start fresh with just the most recent words
            if DEBUG:
                print(
                    f"  Accumulated too many words without match ({len(self.accumulated_words)} vs {len(expected_words)} expected)")
                print(f"  Keeping last {len(expected_words)} words and continuing...")
            self.accumulated_words = self.accumulated_words[-len(expected_words):]

        return self.current_position

    def check_and_execute_commands(self, position):
        """Check if we've reached any commands and execute them."""
        for idx, (command_word_index, command_content) in enumerate(self.commands):
            if idx not in self.executed_commands and position >= command_word_index:
                # Check for meta-command RESET()
                if command_content.strip().upper() == "RESET()":
                    print(f"\n>>> Meta-command RESET() triggered at word {command_word_index}")
                    self.executed_commands.add(idx)
                    self.reset()
                elif command_content.strip().startswith("td:"):
                    # Strip the "td:" prefix and send the raw command string to TD
                    raw = command_content.strip()[3:].strip()
                    print(f"\n>>> TD command at word {command_word_index}: [{raw}]")
                    self.ws_client.send_command(raw, target="td")
                    self.executed_commands.add(idx)
                else:
                    print(f"\n>>> Executing command at word {command_word_index}: [{command_content}]")
                    self.ws_client.send_command(command_content)
                    self.executed_commands.add(idx)

    def process_audio(self):
        """Process audio from microphone."""
        words = self.recognizer.process_audio()

        if words:
            # Normalize recognized words to match script normalization
            # Join and re-normalize to handle any punctuation in recognized text
            raw_text = ' '.join(words)
            normalized_words = normalize_text_for_matching(raw_text)

            if normalized_words:
                # Add to both full history and sentence accumulator
                self.recognized_words.extend(normalized_words)
                self.accumulated_words.extend(normalized_words)

                print(f"Recognized: {raw_text}")
                if DEBUG:
                    print(f"  Normalized: {' '.join(normalized_words)}")
                    print(f"  Total words recognized: {len(self.recognized_words)}")
                    print(f"  Accumulated for matching: {len(self.accumulated_words)}")

                # Update position (tries to match accumulated words to next sentence)
                new_position = self.find_position_in_script()

                # Show progress and next words to say
                if new_position > self.current_position:
                    # Get next sentence to say
                    next_sentence_text = ""
                    if self.current_sentence_idx < len(self.sentences):
                        _, _, next_sentence_text = self.sentences[self.current_sentence_idx]
                        # Show first 80 chars
                        if len(next_sentence_text) > 80:
                            next_sentence_text = next_sentence_text[:80] + "..."

                    progress_pct = int((new_position / len(self.script_words)) *
                                       100) if len(self.script_words) > 0 else 0
                    print(
                        f"Progress: {self.current_position} → {new_position} / {len(self.script_words)} words ({progress_pct}%)")

                    if next_sentence_text:
                        print(f"  Say next: {next_sentence_text}")
                    else:
                        print(f"  ✓ Script complete!")

                    self.current_position = new_position
                    self.check_and_execute_commands(self.current_position)

                # Always send position update to interpreter (for UI)
                self.ws_client.send_position(
                    self.current_position,
                    len(self.script_words),
                    self.script_words,
                    self.plain_text,
                    target="browser"
                )
                self.ws_client.send_position(
                    self.current_position,
                    len(self.script_words),
                    self.script_words,
                    self.plain_text,
                    target="td"
                )

    def draw_ui(self):
        """Draw status window."""
        self.screen.fill((0, 0, 0))

        # Position indicator with progress bar
        y = 20
        progress_pct = int((self.current_position / len(self.script_words)) * 100) if len(self.script_words) > 0 else 0
        position_text = f"Position: {self.current_position}/{len(self.script_words)} ({progress_pct}%)"
        text_surface = self.font.render(position_text, True, (200, 200, 200))
        self.screen.blit(text_surface, (10, y))

        # Sentence progress
        y += 40
        sentence_text = f"Sentence: {self.current_sentence_idx + 1}/{len(self.sentences)}"
        text_surface = self.small_font.render(sentence_text, True, (150, 150, 200))
        self.screen.blit(text_surface, (10, y))

        # Accumulated words for current sentence
        y += 35
        accumulated = ' '.join(self.accumulated_words[-8:])  # Show last 8 words
        if len(self.accumulated_words) > 8:
            accumulated = "..." + accumulated
        heard_text = f"Accumulated: {accumulated}" if accumulated else "Accumulated: (waiting...)"
        text_surface = self.small_font.render(heard_text, True, (100, 200, 100))
        self.screen.blit(text_surface, (10, y))

        # Next sentence to say (helpful prompt)
        y += 35
        if self.current_sentence_idx < len(self.sentences):
            _, _, next_sentence_text = self.sentences[self.current_sentence_idx]
            # Truncate if too long (fit in window width)
            max_chars = 80
            if len(next_sentence_text) > max_chars:
                next_sentence_text = next_sentence_text[:max_chars] + "..."
            next_text = f"Say next: {next_sentence_text}"
            text_surface = self.small_font.render(next_text, True, (255, 215, 0))  # Gold color
            self.screen.blit(text_surface, (10, y))
        else:
            text_surface = self.small_font.render("✓ Script complete!", True, (100, 255, 100))
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

    def advance_to_next_sentence(self):
        """Manually advance to the next sentence (for testing/manual control)."""
        if self.current_sentence_idx >= len(self.sentences):
            print("Already at end of script")
            return

        # Get current sentence end position
        _, sentence_end, sentence_text = self.sentences[self.current_sentence_idx]

        print(f"\n>>> ADVANCING TO NEXT SENTENCE <<<")
        print(f"  Skipping: {sentence_text[:60]}...")

        # Move to end of current sentence
        self.current_position = sentence_end
        self.current_sentence_idx += 1
        self.accumulated_words.clear()

        # Execute any commands we passed
        self.check_and_execute_commands(self.current_position)

        # Show next sentence
        if self.current_sentence_idx < len(self.sentences):
            _, _, next_sentence_text = self.sentences[self.current_sentence_idx]
            print(f"  Next: {next_sentence_text[:60]}...")
        else:
            print("  ✓ Reached end of script!")

        # Update UI
        self.ws_client.send_position(
            self.current_position,
            len(self.script_words),
            self.script_words,
            self.plain_text,
            target="browser"
        )
        self.ws_client.send_position(
            self.current_position,
            len(self.script_words),
            self.script_words,
            self.plain_text,
            target="td"
        )

    def reset(self):
        """Reset recognition state."""
        print("\n>>> RESET <<<")
        self.recognized_words = []
        self.accumulated_words = []
        self.current_position = 0
        self.current_sentence_idx = 0
        self.executed_commands = set()
        self.recognizer.reset()

        # Reset browser - clear graphics and reset position
        self.ws_client.send_command("clear()", target="browser")
        self.ws_client.send_position(
            self.current_position,
            len(self.script_words),
            self.script_words,
            self.plain_text,
            target="browser"
        )

        # Reset TouchDesigner - clear graphics and reset position
        self.ws_client.send_command("clear()", target="td")
        self.ws_client.send_position(
            self.current_position,
            len(self.script_words),
            self.script_words,
            self.plain_text,
            target="td"
        )

    def run(self):
        """Main loop."""
        # Open audio stream
        self.recognizer.start_stream(frames_per_buffer=4000)

        print("="*60)
        print("REAL-TIME LISTENER")
        print("="*60)
        print(f"Script: {self.script_path}")
        print(f"Words: {len(self.script_words)}")
        print(f"Commands: {len(self.commands)}")
        print("\nControls:")
        print("  SPACE - Manually advance to next sentence")
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
                        elif event.key == pygame.K_SPACE:
                            self.advance_to_next_sentence()

                # Process audio
                self.process_audio()

                # Update UI
                self.draw_ui()

                clock.tick(30)

        finally:
            self.recognizer.cleanup()
            self.ws_client.close()
            pygame.quit()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Real-time script listener")
    parser.add_argument("script", help="Path to .script file")
    parser.add_argument(
        "--recognizer",
        choices=["vosk", "whisper"],
        default="vosk",
        help="Speech recognizer to use (default: vosk)"
    )
    parser.add_argument(
        "--model",
        default=None,
        help="Optional: Custom model path (Vosk) or model name (Whisper: tiny/base/small/medium/large). Vosk auto-detects if not specified."
    )
    parser.add_argument("--debug", action="store_true", help="Enable debug output")

    args = parser.parse_args()

    if args.debug:
        DEBUG = True

    try:
        listener = RealtimeListener(args.script, recognizer_type=args.recognizer, model_path=args.model)
        listener.run()
    except ImportError:
        print("\nFailed to initialize recognizer. Please check dependencies and try again.")
        sys.exit(1)
