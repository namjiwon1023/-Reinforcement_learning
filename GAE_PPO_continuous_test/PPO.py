import os
import numpy as np
import torch as T
import torch.nn as nn
import torch.optim as optim
from torch.distributions.normal import Normal

class PPOMemory:
    def __init__(self, batch_size):
        self.states = []
        self.probs = []
        self.vals = []
        self.actions = []
        self.rewards = []
        self.dones = []

        self.batch_size = batch_size

    def generate_batches(self):
        n_states = len(self.states)
        batch_start = np.arange(0, n_states, self.batch_size)
        indices = np.arange(n_states, dtype=np.int64)
        np.random.shuffle(indices)
        batches = [indices[i:i+self.batch_size] for i in batch_start]

        return np.array(self.states),\
                np.array(self.actions),\
                np.array(self.probs),\
                np.array(self.vals),\
                np.array(self.rewards),\
                np.array(self.dones),\
                batches

    def store_memory(self, state, action, prob, vals, reward, done):
        self.states.append(state)
        self.actions.append(action)
        self.probs.append(prob)
        self.vals.append(vals)
        self.rewards.append(reward)
        self.dones.append(done)

    def clear_memory(self):
        self.states = []
        self.probs = []
        self.actions = []
        self.rewards = []
        self.dones = []
        self.vals = []

class ActorNetwork(nn.Module):
    def __init__(self,  input_dims, n_actions, alpha,
                hidden_size=256, max_log_std=2, min_log_std=-20, chkpt_dir='/home/nam/Reinforcement_learning/GAE_PPO_continuous_test'):
        super(ActorNetwork, self).__init__()
        self.max_log_std = max_log_std
        self.min_log_std = min_log_std
        self.checkpoint_file = os.path.join(chkpt_dir, 'actor_torch_ppo')
        self.feature = nn.Sequential(nn.Linear(input_dims, hidden_size),
                                    nn.ReLU())
        self.mean = nn.Sequential(
            nn.Linear(hidden_size, hidden_size),nn.ReLU(),
            nn.Linear(hidden_size, n_actions)
        )
        self.log_std = nn.Sequential(
            nn.Linear(hidden_size, hidden_size),nn.ReLU(),
            nn.Linear(hidden_size, n_actions)
        )

        self.optimizer = optim.Adam(self.parameters(), lr=alpha)
        self.device = T.device('cuda:0' if T.cuda.is_available() else 'cpu')
        self.to(self.device)

    def forward(self, state):
        feature = self.feature(state)
        mu = self.mean(feature)
        log_std = self.log_std(feature)
        log_std = T.clamp(log_std, self.min_log_std, self.max_log_std)
        std = T.exp(log_std)
        dist = Normal(mu, std)

        return dist

    def save_checkpoint(self):
        T.save(self.state_dict(), self.checkpoint_file)

    def load_checkpoint(self):
        self.load_state_dict(T.load(self.checkpoint_file))

class CriticNetwork(nn.Module):
    def __init__(self, input_dims, alpha, hidden_size=256, chkpt_dir='/home/nam/Reinforcement_learning/GAE_PPO'):
        super(CriticNetwork, self).__init__()

        self.checkpoint_file = os.path.join(chkpt_dir, 'critic_torch_ppo')
        self.critic = nn.Sequential(
            nn.Linear(input_dims, hidden_size),
            nn.ReLU(),
            nn.Linear(hidden_size, hidden_size),
            nn.ReLU(),
            nn.Linear(hidden_size, 1)
        )

        self.optimizer = optim.Adam(self.parameters(), lr=alpha)
        self.device = T.device('cuda:0' if T.cuda.is_available() else 'cpu')
        self.to(self.device)

    def forward(self, state):

        value = self.critic(state)

        return value

    def save_checkpoint(self):
        T.save(self.state_dict(), self.checkpoint_file)

    def load_checkpoint(self):
        self.load_state_dict(T.load(self.checkpoint_file))

class PPOAgent:
    def __init__(self, input_dims, n_actions, gamma=0.99, alpha=0.0003, gae_lambda=0.95,
                    policy_clip=0.2, batch_size=64, N=2048, n_epochs=10):
        self.gamma = gamma
        self.policy_clip = policy_clip
        self.n_epochs = n_epochs
        self.gae_lambda = gae_lambda

        self.n_actions = n_actions

        self.actor = ActorNetwork(input_dims, n_actions, alpha)
        self.critic = CriticNetwork(input_dims, alpha)
        self.memory = PPOMemory(batch_size)

    def remember(self, state, action, probs, vals, reward, done):
        self.memory.store_memory(state, action, probs, vals, reward, done)

    def save_models(self):
        print('... save models ...')
        self.actor.save_checkpoint()
        self.critic.save_checkpoint()

    def load_models(self):
        print('... loading models ...')
        self.actor.load_checkpoint()
        self.critic.load_checkpoint()

    def choose_action(self, observation):
        # print('obs shape : ',observation)
        # state = T.tensor([observation], dtype=T.float).to(self.actor.device)
        state = T.FloatTensor(observation).to(self.actor.device)
        # print('state shape : ',state.size())
        # print('state  : ',state)
        # state = T.unsqueeze(T.FloatTensor([observation]).to(self.actor.device), dim=0)
        # state = observation
        dist = self.actor(state)
        value = self.critic(state)
        action = dist.sample()
        # print('action : ',action)

        # Transform the data
        prob = dist.log_prob(action)
        # prob = dist.log_prob(action)
        # print('prob shape', prob.size())
        # print('prob', prob)
        # action = T.squeeze(action).item()
        value = value.item()

        return action.cpu().numpy(), prob.cpu().detach().numpy(), value

    def learn(self):
        for _ in range(self.n_epochs):
            state_arr, action_arr, old_prob_arr, vals_arr, reward_arr, done_arr, batches = self.memory.generate_batches()

            values = vals_arr
            advantage = np.zeros(len(reward_arr), dtype=np.float32)

            for t in range(len(reward_arr)-1):
                discount = 1
                a_t = 0
                for k in range(t, len(reward_arr)-1):
                    a_t += discount*(reward_arr[k] + self.gamma*values[k+1]*(1-int(done_arr[k])) - values[k])
                    discount *= self.gamma*self.gae_lambda
                advantage[t] = a_t
            # advantage=T.tensor(advantage).to(self.actor.device)
            advantage=T.FloatTensor(advantage).to(self.actor.device)

            # values = T.tensor(values).to(self.actor.device)
            values = T.FloatTensor(values).to(self.actor.device)
            # print('values', values)
            for batch in batches:
                # states = T.tensor(state_arr[batch], dtype=T.float).to(self.actor.device)
                states = T.FloatTensor(state_arr[batch]).to(self.actor.device)
                # old_probs = T.tensor(old_prob_arr[batch]).to(self.actor.device)
                old_probs = T.FloatTensor(old_prob_arr[batch]).to(self.actor.device)
                # actions = T.tensor(action_arr[batch]).to(self.actor.device)
                actions = T.FloatTensor(action_arr[batch]).reshape(-1, self.n_actions).to(self.actor.device)
                # actions = action_arr[batch]

                dist = self.actor(states)
                critic_value = self.critic(states)
                # print('critic_value', critic_value)

                critic_value = T.squeeze(critic_value)
                # print('critic_value', critic_value)
                entropy = dist.entropy().mean()

                new_probs = dist.log_prob(actions)
                prob_ratio = new_probs.exp() / old_probs.exp()
                # prob_ratio = (new_probs - old_probs).exp()
                weighted_probs = advantage[batch] * prob_ratio
                weighted_clipped_probs = T.clamp(prob_ratio, 1-self.policy_clip, 1+self.policy_clip)*advantage[batch]
                actor_loss = -T.min(weighted_probs, weighted_clipped_probs).mean()

                returns = advantage[batch] + values[batch]
                #print('returns',returns)
                critic_loss = (returns-critic_value)**2
                critic_loss = critic_loss.mean()

                total_loss = actor_loss + 0.5*critic_loss - 0.001*entropy
                self.actor.optimizer.zero_grad()
                self.critic.optimizer.zero_grad()
                total_loss.backward()
                self.actor.optimizer.step()
                self.critic.optimizer.step()

        self.memory.clear_memory()