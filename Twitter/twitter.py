import tweepy
from tweepy import OAuthHandler, Stream
from tweepy.streaming import StreamListener
import time
import json
from SentimentAnalyze import SentimentAnalyzer
from Database.db_mySql import MySqlDbConnector
import pandas as pd
import numpy as np
from Service.AskCoincap import CoinIoReader
from sqlalchemy import create_engine


class CryptoListner(StreamListener):
    def __init__(self):
        self.analyzer = SentimentAnalyzer()
       # self.db_connector= MySqlDbConnector('localhost', 3306, 'root', '', 'coindata')
       # self.db_connector.create_tweets_tabel()
        self.engine = create_engine('mysql+mysqldb://root:@localhost:3306/coindata', echo=False)
        self.coin_cap_reader=CoinIoReader()
        self.tweet_array= np.empty((1,8))

    def __wait_till_start(self):
        from datetime import datetime
        while datetime.now().minute % 40 != 0:
            time.sleep(1)
            print(datetime.now())
        print('Starting at' + str(datetime.now()))

    def __get_actual_btc_price(self):
        btc_price=json.loads(self.coin_cap_reader.getCoinCapData('page/BTC').text)
        return btc_price['price']

    def __get_btc_and_wait(self, time_to_wait, range=50):
        start_time = time.time()
        start_price = self.__get_actual_btc_price()
        act_time = time.time()

        time_to_sleep = time_to_wait - (act_time - start_time)
        time.sleep(time_to_sleep)

        end_price = self.__get_actual_btc_price()

        price_diff = end_price - start_price

        if end_price > start_price+range:
            price_diff=1
        elif end_price < start_price-range:
            price_diff = -1
        elif start_price-range < end_price < start_price+range:
            price_diff = 0

        return price_diff, start_price, end_price

    def authenticate_on_twitter(self):
        json_keys = open("keys.json").read()
        keys = json.loads(json_keys)
        auth = OAuthHandler(keys["consumer_key"], keys["consumer_secret"])
        auth.set_access_token(keys["access_token"], keys["access_secret"])

        api = tweepy.API(auth)
        return auth

    def __format_tweet_as_array(self, tweet_as_json):
        all_data = json.loads(tweet_as_json)
        sentiment = self.analyzer.analyze_tweet(all_data['text'])

        if all_data['retweeted']:
            is_retweeted = 1
        elif not all_data['retweeted']:
            is_retweeted = 0

        tweet_as_array=np.asarray([all_data['text'],is_retweeted,all_data['retweet_count'], sentiment['pos'],
                                   sentiment['neg'], sentiment['neu'], sentiment['compound'], 0])

        return tweet_as_array

    def __array_in_dataframe(self, price_diff, start_price, end_price):
        tweet_array=self.tweet_array[:]
        self.tweet_array=np.empty((1, 8))
        d=np.full((len(tweet_array)),price_diff)
        s = np.full((len(tweet_array)), start_price)
        e = np.full((len(tweet_array)), end_price)
        tweet_array= np.column_stack([tweet_array, d,s,e])

        data={ 'text':tweet_array[:, 0],
               'retweeted': tweet_array[:, 1],
               'retweet_count': tweet_array[:, 2],
               'sentiment_pos': tweet_array[:, 3],
               'sentiment_neg': tweet_array[:, 4],
               'sentiment_neu': tweet_array[:, 5],
               'sentiment_comp':tweet_array[:, 6],
               'price_diff':tweet_array[:, 7],
               'start_price':tweet_array[:, 8],
               'end_price':tweet_array[:, 9]}
        df= pd.DataFrame(data, columns=['text', 'retweeted', 'retweet_count', 'sentiment_pos',
                                        'sentiment_neg', 'sentiment_neu', 'sentiment_comp','price_diff',
                                        'start_price', 'end_price'])

        return df

    def write_to_db(self, dataframe):
        dataframe.to_sql(name = 'tweets', con = self.engine, if_exists = 'append', index = False)


    def on_data(self, data):
        try:
            tweet = self.__format_tweet_as_array(data)

            self.tweet_array= np.vstack([self.tweet_array, tweet])
            return True
        except BaseException as e:
            print("Error on_data: %s" % str(e))
        return True

    def on_error(self, status):
        print(status)
        return True

    def stream_tweets(self):
        auth=self.authenticate_on_twitter()
        twitter_stream = Stream(auth, self)
        twitter_stream.filter(languages=['en'],
                              track=['#BTC', '#bitcoin', '#eth', '#iota' '#ETH', '#dash', '#DASH', '#crypto',
                               '#cryptocurrency', '#bitcoin cash', '#bch', '#XRP', '#BCH'], async=True)

    def mine_tweets(self):
        #self.__wait_till_start()
        self.stream_tweets()
        while True:
            diff, start, end= self.__get_btc_and_wait(20)
            print("startprice: %.2f endprice: %.2f" %(start,end))
            df=self.__array_in_dataframe(diff, start, end)
            self.write_to_db(df)


if __name__ == "__main__":
    tw= CryptoListner()
    tw.mine_tweets()