import random
from collections import defaultdict

class MarkovModel:
    """
    A simple 1st-order Markov Model for predicting the next discrete integer
    in a sequence.
    """
    def __init__(self):
        # Dictionary mapping a state to another dictionary of next states and their counts
        self.transitions = defaultdict(lambda: defaultdict(int))

    def train(self, sequence):
        """
        Trains the Markov Model using a sequence of discrete integers.

        Args:
            sequence (list of int): A list of integers representing the sequence.
        """
        if not sequence or len(sequence) < 2:
            return

        for i in range(len(sequence) - 1):
            current_state = sequence[i]
            next_state = sequence[i + 1]
            self.transitions[current_state][next_state] += 1

    def predict_next(self, current_state):
        """
        Predicts the next number based on the current state.
        Chooses the next number probabilistically based on the learned transition weights.

        Args:
            current_state (int): The current integer state.

        Returns:
            int or None: The predicted next integer, or None if the current state
                         is unseen or has no known transitions.
        """
        if current_state not in self.transitions or not self.transitions[current_state]:
            return None

        next_states = list(self.transitions[current_state].keys())
        weights = list(self.transitions[current_state].values())

        # random.choices returns a list of k elements, we take the first (and only) one
        return random.choices(next_states, weights=weights, k=1)[0]
