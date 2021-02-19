import torch
import torch.nn as nn
import torch.nn.functional as F
import torch.optim as optim
import numpy as np
import pickle
import os

from CriticNet import CriticNet
from ReplayBuffer import ReplayBuffer
from CommunicationEnv import CommunicationEnv

device = torch.device("cuda" if torch.cuda.is_available() else "cpu")

class DDQNAgent(object):
    def __init__(self, **kwargs):
        for key, value in kwargs.items():
            setattr(self, key, value)

        self.eval_net = CriticNet(self.input_dims, self.action_size).to(device)
        self.target_net = CriticNet(self.input_dims, self.action_size).to(device)
        self.target_net.load_state_dict(self.eval_net.state_dict())
        self.target_net.eval()

        self.memory = ReplayBuffer(self.memory_size, self.batch_size)
        self.transition = list()

        self.optimizer = optim.SGD(self.eval_net.parameters(),lr=self.lr)
        self.loss = nn.MSELoss()

        self.C_L = 0.
        self.Q_V = 0.
        self.chkpt_dir = '/home/nam/Reinforcement_learning/Interference_Avoidance'
        self.checkpoint_file = os.path.join(self.chkpt_dir, 'ddqn')

        if self.load_model :
            self.eval_net.load_state_dict(torch.load(self.checkpoint_file))

    def choose_action(self, state):

        s = torch.FloatTensor(state).to(device)

        if self.epsilon > np.random.random():
            choose_action = np.random.randint(0,self.action_size)
        else :
            choose_action = self.eval_net(s).to(device).argmax()
            choose_action = choose_action.detach().cpu().numpy()
        self.transition = [state, choose_action]
        return choose_action

    def target_net_update(self):

        if self.update_counter % self.update_time == 0 :
            self.target_net.load_state_dict(self.eval_net.state_dict())
        self.update_counter += 1


    def learn(self):

        self.target_net_update()
        samples = self.memory.sample_batch()

        state = torch.FloatTensor(samples['obs']).to(device)
        next_state = torch.FloatTensor(samples['next_obs']).to(device)
        action = torch.LongTensor(samples['act']).reshape(-1,6).to(device)
        reward = torch.FloatTensor(samples['rew']).reshape(-1,1).to(device)
        done = torch.FloatTensor(samples['done']).reshape(-1,1).to(device)

        curr_q = self.eval_net(state).gather(1, action)
        self.Q_V = curr_q.detach().cpu().numpy()
        next_q = self.target_net(next_state).gather(1, self.eval_net(next_state).argmax(dim = 1, keepdim = True)).detach()

        mask = 1 - done

        target_q = (reward + self.gamma * next_q * mask).to(device)

        loss = self.loss(curr_q, target_q)
        self.C_L = loss.detach().cpu().numpy()

        self.optimizer.zero_grad()
        loss.backward()
        self.optimizer.step()


if __name__ == "__main__":

    params = {
                'memory_size' : 2000,
                'batch_size' : 5,
                'input_dims' : 3,
                'action_size' : 6,
                'epsilon' : 0.1,
                'startTime' : 20,
                'update_time' : 10,
                'update_counter' : 0,
                'gamma' : 0.4,
                'lr' : 0.1,
                'load_model' : False,
                'load_episode' : 0,
        }

    agent = DDQNAgent(**params)

    env = CommunicationEnv()
    critic_losses = []
    scores = []
    Q_Values = []

    n_steps = 0
    N = 20
    learn_iters = 0

    for e in range(agent.load_episode, 10000):

        s = env.reset(input_ph3=False, input_phj=False)
        score = 0.
        step = 0

        np.savetxt("./Total_reward.txt",scores, delimiter=",")
        np.savetxt("./critic_loss.txt",critic_losses, delimiter=",")
        np.savetxt("./Q_value.txt",Q_Value, delimiter=",")

        if e % 10 == 0 :
            torch.save(agent.eval_net.state_dict(), agent.dirPath + str(e) + '.h5')

        for t in range(6000):
        # while not done:

            a = agent.choose_action(s)

            s_, r, done = env.step(a)

            agent.transition += [r, s_, done]

            agent.memory.store(*agent.transition)

            if n_steps == agent.startTime:
                if n_steps % N == 0:
                    agent.learn()
                    learn_iters += 1

            loss = agent.C_L
            score += r
            s = s_

            print('Episode : {} Step : {} learn_iters : {} Action : {} Reward : {} Loss : {}'.format(e, step ,learn_iters ,a, r, loss))
            n_steps += 1

            if done:

                scores.append(score)
                Q_Values.append(agent.Q_V)
                critic_losses.append(agent.C_L)
                break

        print('|============================================================================================|')
        print('|=========================================  Result  =========================================|')
        print('|                                     Total_Step : {}  '.format(n_steps))
        print('|                      Episode : {} Total_Reward : {} '.format(e, score))
        print('|============================================================================================|')

    print('Finish.')