import unittest
from markov_model import MarkovModel

class TestMarkovModel(unittest.TestCase):
    def test_training_and_transitions(self):
        model = MarkovModel()
        sequence = [1, 2, 1, 3, 1, 2]
        model.train(sequence)

        # 1 goes to 2 (twice) and to 3 (once)
        self.assertEqual(model.transitions[1][2], 2)
        self.assertEqual(model.transitions[1][3], 1)

        # 2 goes to 1 (once)
        self.assertEqual(model.transitions[2][1], 1)

        # 3 goes to 1 (once)
        self.assertEqual(model.transitions[3][1], 1)

    def test_predict_next_deterministic(self):
        model = MarkovModel()
        model.train([4, 5, 4, 5])

        # 4 always goes to 5
        self.assertEqual(model.predict_next(4), 5)
        # 5 always goes to 4
        self.assertEqual(model.predict_next(5), 4)

    def test_predict_next_probabilistic(self):
        model = MarkovModel()
        # Train with a sequence where 1 goes to 2 a lot, and 3 a little
        sequence = [1, 2] * 90 + [1, 3] * 10
        model.train(sequence)

        results = {2: 0, 3: 0}
        for _ in range(1000):
            res = model.predict_next(1)
            results[res] += 1

        # We expect roughly 90% 2s and 10% 3s
        self.assertTrue(800 < results[2] < 1000)
        self.assertTrue(0 < results[3] < 200)

    def test_predict_next_unseen_state(self):
        model = MarkovModel()
        model.train([1, 2, 3])

        # 4 is an unseen state
        self.assertIsNone(model.predict_next(4))

        # 3 is seen, but has no transitions (it's the last element)
        self.assertIsNone(model.predict_next(3))

if __name__ == '__main__':
    unittest.main()
