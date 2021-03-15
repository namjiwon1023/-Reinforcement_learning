import os
import torch as T
import torch.nn as nn
import torch.optim as optim
import torch.nn.functional as F
import numpy as np
import copy
import gym

from ReplayBuffer import ReplayBuffer
from ActorNetwork import Actor
from CriticNetwork import CriticQ, CriticV

if torch.backends.cudnn.enabled:
    torch.backends.cudnn.benchmark = False
    torch.backends.cudnn.deterministic = True

seed = 123
torch.manual_seed(seed)
np.random.seed(seed)
random.seed(seed)

device = T.device('cuda' if T.cuda.is_available() else 'cpu')

class SACAgent:
    def __init__(self, **kwargs):
        for key, value in kwargs.items():
            setattr(self, key, value)

        self.env = gym.make('Pendulum-v0')

        self.n_states = self.env.observation_space.shape[0]
        self.n_actions = self.env.action_space.shape[0]
        self.max_action = float(self.env.action_space.high[0])

        self.memory = ReplayBuffer(self.memory_size, self.n_states, self.batch_size)

        self.target_entropy = -np.prod((self.n_actions,)).item()
        self.log_alpha = T.zeros(1, requires_grad=True, device=device)

        self.actor = Actor(self.n_states, self.n_actions).to(device)

        self.vf = CriticV(self.n_states).to(device)
        self.vf_target = copy.deepcopy(vf)

        self.qf_1 = CriticQ(self.n_states + self.n_actions).to(device)
        self.qf_2 = CriticQ(self.n_states + self.n_actions).to(device)

        self.alpha_optimizer = optim.Adam([self.log_alpha], lr=3e-4)
        self.actor_optimizer = optim.Adam(self.actor.parameters(), lr=3e-4)

        self.vf_optimizer = optim.Adam(self.vf.parameters(), lr=3e-4)
        self.qf_1_optimizer = optim.Adam(self.qf_1.parameters(), lr=3e-4)
        self.qf_2_optimizer = optim.Adam(self.qf_2.parameters(), lr=3e-4)

        self.transition = list()

        self.total_step = 0

    def choose_action(self, state):
        if self.total_step < self.initial_random_steps and not self.test_model:
            action = self.env.action_space.sample()
        else:
            action = self.actor(T.FloatTensor(state).to(device))[0].detach().cpu().numpy()
        self.transition = [state, action]
        return action

    def target_soft_update(self):
        tau = self.tau
        for t_p, l_p in zip(self.vf_target.parameters(), self.vf.parameters()):
            t_p.data.copy_(tau * l_p.data + (1 - tau) * t_p.data)

    def learn(self):
        samples = self.memory.sample_batch()
        state = T.FloatTensor(samples["state"]).to(device)
        next_state = T.FloatTensor(samples["next_state"]).to(device)
        action = T.FloatTensor(samples["action"].reshape(-1, 1)).to(device)
        reward = T.FloatTensor(samples["reward"].reshape(-1, 1)).to(device)
        done = T.FloatTensor(samples["done"].reshape(-1, 1)).to(device)

        new_action, log_prob = self.actor(state)

        alpha_loss = (-self.log_alpha.exp() * (log_prob + self.target_entropy).detach()).mean()

        self.alpha_optimizer.zero_grad()
        alpha_loss.backward()
        self.alpha_optimizer.step()

        alpha = self.log_alpha.exp()

        mask = 1 - done
        q_1_pred = self.qf_1(state, action)
        q_2_pred = self.qf_2(state, action)
        v_target = self.vf_target(next_state)
        q_target = reward + self.gamma * v_target * mask
        qf_1_loss = F.mse_loss(q_1_pred, q_target.detach())
        qf_2_loss = F.mse_loss(q_2_pred, q_target.detach())

        v_pred = self.vf(state)
        q_pred = T.min(self.qf_1(state, new_action), self.qf_2(state, new_action))

        v_target = q_pred - alpha * log_prob
        vf_loss = F.mse_loss(v_pred, vf_target.detach())

        if self.total_step % self.update_time == 0 :
            advantage = q_pred - v_pred.detach()
            actor_loss = (alpha * log_prob - advantage).mean()

            self.actor.optimizer.zero_grad()
            actor_loss.backward()
            self.actor.optimizer.step()

            self.target_soft_update()
        else:
            actor_loss = T.zeros(1)

        self.qf_1_optimizer.zero_grad()
        qf_1_loss.backward()
        self.qf_1_optimizer.step()

        self.qf_2_optimizer.zero_grad()
        qf_2_loss.backward()
        self.qf_2_optimizer.step()

        qf_loss = qf_1_loss + qf_2_loss

        self.vf_optimizer.zero_grad()
        vf_loss.backward()
        self.vf_optimizer.step()