"""
Game Manager - Records and replays entire games.

Records game state snapshots after every significant action so that
the full game can be saved, loaded, and replayed move-by-move.
"""
import json


class SHCGGameManager:
    """Records and replays entire games as a sequence of state snapshots."""

    def __init__(self):
        self.recording: list[dict] = []   # [{turn, description, state}]
        self.replay_index: int = -1       # current position in replay (-1 = not replaying)
        self.is_replaying: bool = False

    # ------------------------------------------------------------------
    # Recording
    # ------------------------------------------------------------------

    def start_recording(self, initial_state_string: str):
        """Begin a new recording with the initial game state."""
        self.recording = [{
            'turn': 1,
            'description': 'Game Start',
            'state': initial_state_string,
        }]
        self.replay_index = -1
        self.is_replaying = False

    def record_action(self, turn: int, description: str, state_string: str):
        """Append the current state as a new action entry.

        Does nothing while in replay mode so that navigating through
        a replay doesn't pollute the recording.
        """
        if self.is_replaying:
            return
        self.recording.append({
            'turn': turn,
            'description': description,
            'state': state_string,
        })

    # ------------------------------------------------------------------
    # Save / Load entire game recording
    # ------------------------------------------------------------------

    def save_game(self, filepath: str):
        """Save the entire game recording to a JSON file."""
        with open(filepath, 'w', encoding='utf-8') as f:
            json.dump({'version': 1, 'moves': self.recording}, f, ensure_ascii=False)

    def load_game(self, filepath: str):
        """Load a game recording from a JSON file and enter replay mode at the start."""
        with open(filepath, 'r', encoding='utf-8') as f:
            data = json.load(f)
        if isinstance(data, list):
            # Backward compat: plain list of moves
            self.recording = data
        elif isinstance(data, dict):
            self.recording = data.get('moves', [])
        else:
            raise ValueError("Unrecognised game recording format.")
        if not self.recording:
            raise ValueError("Game recording is empty.")
        self.replay_index = 0
        self.is_replaying = True

    # ------------------------------------------------------------------
    # Replay navigation
    # ------------------------------------------------------------------

    def get_total_moves(self) -> int:
        """Total number of recorded snapshots."""
        return len(self.recording)

    def get_current_index(self) -> int:
        return self.replay_index

    def get_current_entry(self) -> dict | None:
        """Return the entry at the current replay index, or None."""
        if 0 <= self.replay_index < len(self.recording):
            return self.recording[self.replay_index]
        return None

    def next_move(self) -> dict | None:
        """Advance one step forward. Returns the entry or None if at end."""
        if self.replay_index < len(self.recording) - 1:
            self.replay_index += 1
            return self.recording[self.replay_index]
        return None

    def prev_move(self) -> dict | None:
        """Go back one step. Returns the entry or None if at start."""
        if self.replay_index > 0:
            self.replay_index -= 1
            return self.recording[self.replay_index]
        return None

    def to_start(self) -> dict | None:
        """Jump to the very first snapshot."""
        if self.recording:
            self.replay_index = 0
            return self.recording[0]
        return None

    def to_end(self) -> dict | None:
        """Jump to the very last snapshot."""
        if self.recording:
            self.replay_index = len(self.recording) - 1
            return self.recording[-1]
        return None

    def to_start_of_turn(self) -> dict | None:
        """Jump to the first action of the current turn.

        If the current position is already the first action of its turn,
        jump to the start of the *previous* turn instead (so the button
        always 'does something').
        """
        if not self.recording or self.replay_index < 0:
            return None
        current_turn = self.recording[self.replay_index]['turn']
        # Find the first entry with this turn number
        first_of_turn = None
        for i, entry in enumerate(self.recording):
            if entry['turn'] == current_turn:
                first_of_turn = i
                break
        if first_of_turn is not None:
            if first_of_turn == self.replay_index and first_of_turn > 0:
                # Already at start of turn → go to previous turn
                prev_turn = self.recording[first_of_turn - 1]['turn']
                for i, entry in enumerate(self.recording):
                    if entry['turn'] == prev_turn:
                        self.replay_index = i
                        return entry
            else:
                self.replay_index = first_of_turn
                return self.recording[first_of_turn]
        return None

    def to_turn(self, turn_number: int) -> dict | None:
        """Jump to the first action of *turn_number*.

        Returns None if the turn does not exist in the recording.
        """
        for i, entry in enumerate(self.recording):
            if entry['turn'] == turn_number:
                self.replay_index = i
                return entry
        return None

    def get_max_turn(self) -> int:
        """Return the highest turn number present in the recording."""
        if not self.recording:
            return 0
        return max(entry['turn'] for entry in self.recording)

    def is_at_end(self) -> bool:
        return self.replay_index >= len(self.recording) - 1

    def is_at_start(self) -> bool:
        return self.replay_index <= 0

    # ------------------------------------------------------------------
    # Replay status helpers
    # ------------------------------------------------------------------

    def get_status_text(self) -> str:
        """Return a short human-readable status string."""
        if not self.is_replaying:
            if self.recording:
                return f"In Game"
            return "Not recording"
        total = len(self.recording)
        idx = self.replay_index + 1
        entry = self.get_current_entry()
        turn = entry['turn'] if entry else '?'
        desc = entry.get('description', '') if entry else ''
        return f"Replay {idx}/{total}  Turn {turn}  {desc}"

    def exit_replay(self):
        """Leave replay mode (does not clear the recording)."""
        self.is_replaying = False
        self.replay_index = -1
