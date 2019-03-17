from mlcore.custom_gym import CustomEnv

__author__ = 'po'

# scheduler
from datetime import datetime, timedelta

# plot indicator charts
import matplotlib.pyplot as plt

# ig services
from dataprovider.ig_service import IGService
# defines username, password, api_key, acc_type
from dataprovider.ig_service_config import *
# libs
from risk_adjusted_metrics import *
from mlcore.rl_agent import torchDQN
import glob
import pandas as pd


# fetch the open high low and close at daily time resolution for the past 20 days for analysis
def getHistoricalData(specificDate):
    ig_service = IGService(username, password, api_key, acc_type)
    ig_service.create_session()

    '''
    # dynamically retrieve the epic/product code
    print("fetch_all_watchlists")
    response = ig_service.fetch_all_watchlists()
    # get "MyWatchlist"
    watchlist_id = response['id'].iloc[2]

    print("fetch_watchlist_markets")
    response = ig_service.fetch_watchlist_markets(watchlist_id)
    print(response)
    epic = response['epic'].iloc[0]

    print("fetch_market_by_epic")
    response = ig_service.fetch_market_by_epic(epic)
    print(response)
    '''

    print("search_pricing")
    # Instrument tag # US500 DFB
    epic = 'IX.D.DOW.IGD.IP'

    # Price resolution (SECOND, MINUTE, MINUTE_2, MINUTE_3, MINUTE_5, MINUTE_10, MINUTE_15, MINUTE_30, HOUR, HOUR_2, HOUR_3, HOUR_4, DAY, WEEK, MONTH)
    resolution = 'MINUTE_5'  # resolution = 'H', '1Min'



    # (yyyy:MM:dd-HH:mm:ss)
    #today = datetime.today()
    #startDate = str(today.date() - timedelta(days=2)).replace("-", ":") + "-00:00:00"
    #endDate = str(today.date() - timedelta(days=0)).replace("-", ":") + "-00:00:00"

    startDate = specificDate.date().strftime('%Y:%m:%d')+"-00:00:00"
    endDate = (specificDate + timedelta(days=1)).date().strftime('%Y:%m:%d')+"-23:55:00"

    response = ig_service.fetch_historical_prices_by_epic_and_date_range(epic, resolution, startDate, endDate)
    return response['prices']



def bulkDownload(date, numberOfDays):
    specificDate = datetime.strptime(date, '%Y-%m-%d')

    # 10 days
    for i in range(numberOfDays):
        if(specificDate.weekday()!=6):
            pastData = getHistoricalData(specificDate)
            saveSpecificDate(pastData,specificDate)
        specificDate -= timedelta(days=1)





def getAverage(dataArray):
    tempList = []
    for priceObject in dataArray:
        if(priceObject['bid']!=None and priceObject['ask']!=None):
            tempList.append(round((priceObject['ask'] + priceObject['bid']) / 2,2))
        else:
            tempList.append(0)
    return tempList


def saveSpecificDate(pastData, date):
    # iterate list of json and average up the results
    pastData['averageOpen'] = getAverage(pastData['openPrice'])
    pastData['averageLow'] = getAverage(pastData['lowPrice'])
    pastData['averageHigh'] = getAverage(pastData['highPrice'])
    pastData['averageClose'] = getAverage(pastData['closePrice'])

    pastData.to_csv("data/"+str(date.date())+".csv")


# construct stochastic indicator to determine momentum in direction using (formula is just highest high - close/ highest high - lowest low)* 100 to get percentage
def constructIndicator(pastData):
    # http://www.andrewshamlet.net/2017/07/13/python-tutorial-stochastic-oscillator/
    # http://www.pythonforfinance.net/2017/10/10/stochastic-oscillator-trading-strategy-backtest-in-python/

    # Create the "lowestLow" column in the DataFrame
    pastData['lowestLow'] = pastData['averageLow'].rolling(window=14).min()

    # Create the "highestHigh" column in the DataFrame
    pastData['highestHigh'] = pastData['averageHigh'].rolling(window=14).max()

    # Create the "%K" column in the DataFrame refer to the function comment for formula of stochastic ociliator
    pastData['%K'] = ((pastData['averageClose'] - pastData['lowestLow']) / (
        pastData['highestHigh'] - pastData['lowestLow'])) * 100


    # save so we can retrain model using most recent data
    #pastData.to_csv("yahoo_finance\\30Min.csv", sep=',', encoding='utf-8')

    # Create the "%D" column in the DataFrame moving average of calculated K
    pastData['%D'] = pastData['%K'].rolling(window=3).mean()

    # drop 14 bar ago cut away parts of chart without indicator
    # pastData.drop(pastData.index[:15], inplace=True)

    fig, axes = plt.subplots(nrows=2, ncols=1, figsize=(20, 10))

    pastData['averageClose'].plot(ax=axes[0]);
    axes[0].set_title('Close')
    pastData[['%K', '%D']].plot(ax=axes[1]);
    axes[1].set_title('Oscillator')
    # plt.show()

    return pastData
    # consider building other indicator



# prints formatted price
def formatPrice(n):
    return ("-$" if n < 0 else "$") + "{0:.2f}".format(abs(n))

# returns the vector containing stock data from a fixed file
def getStockClosingDataVec(key):
    vec = []
    lines = open("yahoo_finance/" + key + ".csv", "r").read().splitlines()

    # ignore header
    for line in lines[1:]:
        # append closing price into list
        vec.append(float(line.split(",")[4]))

    return vec

# returns the sigmoid
def sigmoid(gamma):
    if gamma < 0:
        return 1 - 1 / (1 + math.exp(gamma))
    return 1 / (1 + math.exp(-gamma))

    # return 1 / (1 + math.exp(-x))

# returns an an n-day state representation ending at time t
def getState(data, t, n):
    d = t - n + 1
    block = data[d:t + 1] if d >= 0 else -d * [data[0]] + data[0:t + 1]  # pad with t0
    res = []
    for i in range(n - 1):
        res.append(sigmoid(block[i + 1] - block[i]))


    return np.array([res])





# measure and evaluate system developed
def performanceTest(returns):
    # Calmar
    # The Calmar ratio discounts the expected excess return of a portfolio by the worst expected maximum draw down for that portfolio,

    # simulation
    # Returns from the portfolio (r) and market (m)
    # returns = nrand.uniform(-1, 1, 50)

    # Expected return
    averageExpectedReturn = np.mean(returns)

    # Risk Free Rate assumption that 6% from other investment as benchmark (Opportunity cost)
    riskFreeRate = 0.06

    print("Calmar Ratio =", calmar_ratio(averageExpectedReturn, returns, riskFreeRate))



def trainMLModel():
    # retrieve data
    allFiles = glob.glob("data/*.csv")

    list_ = []
    for file_ in allFiles:
        df = pd.read_csv(file_,sep=',',index_col=0, header=0)
        list_.append(df)
    # concatenate every row in the list and reset index to sequential
    pastData = pd.concat(list_, axis = 0, ignore_index = True)


    # setsnapshotTime as index
    pastDataAsState = pastData[['snapshotTime','averageOpen','averageHigh','averageLow','averageClose','lastTradedVolume']]
    pastDataAsState.snapshotTime = pd.to_datetime(pastData['snapshotTime'], format='%Y:%m:%d-%H:%M:%S')
    pastDataAsState.set_index('snapshotTime', inplace=True)
    print(pastDataAsState.head())
    # print(pastDataAsState.info())
    # asd=pastDataAsState.iloc[0,:]
    # print(pastDataAsState.loc['2019-02-01'])
    # print(type(pastDataAsState.loc['2019-02-01']))

    # initialise gym environment with single day slice of past data
    env=CustomEnv(pastDataAsState.loc['2019-02-19'])

    dqn = torchDQN()
    total_reward = []
    total_action = []
    print('\nCollecting experience...')
    # trade the same day 400 times
    for i_episode in range(400):
        s = env.reset()
        ep_r = 0
        while True:
            #env.render()
            # see how random trading with 2:1 RRR will perform
            #a = np.random.randint(0, 3)

            a = dqn.choose_action(s)
            total_action.append(a)
            # take action
            s_, r, done, info = env.step(a)

            # modify the reward
            # x, x_dot, theta, theta_dot = s_
            # r1 = (env.x_threshold - abs(x)) / env.x_threshold - 0.8
            # r2 = (env.theta_threshold_radians - abs(theta)) / env.theta_threshold_radians - 0.5
            # r = r1 + r2

            dqn.store_transition(s, a, r, s_)

            ep_r += r

            # every 10k steps we train our model both eval and target
            if dqn.memory_counter > 10000:
                # but target updates at a slower rate so learning is more stable
                # think of eval as the hyper active child and target as the parent that critics the child exploration
                dqn.learn()



            if done:
                print('Ep: ', i_episode, '| Ep_r: ', round(r, 2))
                ep_r = r
                break
            s = s_
        total_reward.append(ep_r)
    import collections
    counter=collections.Counter(total_action)
    print("total unique action ", print(counter))

    plt.title('Reward')
    plt.xlabel('No of Episodes')
    plt.ylabel('Total reward')
    plt.plot(np.arange(len(total_reward)), total_reward, 'r-', lw=5)

    plt.show()
    #dqn.save()


def evaluateMLModel():
    pass


def automateTrading():

    pass
    # pastDataWithIndicator = constructIndicator(pastData)

    # using past 20 day data
    # machineLearning(pastData)



'''
what is the key outcome?
1) reinforcement to trade profitably daily basis (pending <-- most likely dqn or rdn)
2) robust when back tested against historical data 2 month (Downloaded)
3) automate trade demo using model and algorithm (completed custom gym environment for agent to interact with based on ig dow jones data in 5min resolution)
4) unrealised profit or loss into state & new action close position
5) check if underfit or overfit model
&) https://www.kaggle.com/itoeiji/deep-reinforcement-learning-on-stock-data

'''
if __name__ == "__main__":

    #bulkDownload('2019-03-13', 4)
    trainMLModel()
    # results = evaluateMLModel()
    # performanceTest(results)

    # automateTrading()
    # proceed to build reinforcement learning and use performanceTest calmar ratio as fitness score



    #TODO after all is set and done final todo is to use it on CFD account