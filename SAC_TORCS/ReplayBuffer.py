import numpy as np

class ReplayBuffer:
    def __init__(self, memory_size, n_states, n_actions, batch_size=32):
        self.state = np.zeros([memory_size, n_states], dtype=np.float32)
        self.next_state = np.zeros([memory_size, n_states], dtype=np.float32)
        self.action = np.zeros([memory_size, n_actions],dtype=np.float32)
        self.reward = np.zeros([memory_size], dtype=np.float32)
        self.done = np.zeros([memory_size], dtype=np.float32)

        self.max_size, self.batch_size = memory_size, batch_size
        self.ptr, self.size, = 0, 0
        self.count = 0

    def store(self, state, action, reward, next_state, done):
        self.state[self.ptr] = state
        self.action[self.ptr] = action
        self.reward[self.ptr] = reward
        self.next_state[self.ptr] = next_state
        self.done[self.ptr] = done

        self.ptr = (self.ptr + 1) % self.max_size
        self.size = min(self.size + 1, self.max_size)
        self.count += 1

    def store_with_store_memory(self, transitions):
        for t in transitions:
            self.store(*t)

    def sample_batch(self):
        if self.count < self.batch_size:
            index = np.random.choice(self.size, self.count)
        else:
            index = np.random.choice(self.size, self.batch_size, replace = False)

        return dict(state = self.state[index],
                    action = self.action[index],
                    reward = self.reward[index],
                    next_state = self.next_state[index],
                    done = self.done[index])

    def __len__(self):
        return self.size