import spotipy
import pandas as pd
from spotipy.oauth2 import SpotifyClientCredentials, SpotifyOAuth
import spotipy.util as util
from tqdm.notebook import tqdm
from dateutil.parser import isoparse as dateparse
from datetime import datetime, timedelta
import pickle
from cluster_classifier import predict
import hashlib
import numpy as np

class RecentScraper():
    def __init__(self, redirect_uri = "http://localhost:8000", token_path = "ref/api.txt", recent_backup_path = "data/recent_backup.csv", recent_path = "data/recent.csv", playlist_path = 'ref/playlists.data', last_session_path = "data/last_session.data", all_path = "data/all_songs_clustered.csv"):
        #load credentials
        with open(token_path, "r") as f:
            self.username, self.client_id, self.client_secret = [x.strip() for x in f]
        
        #load Spotify client
        scope = "user-read-recently-played playlist-modify-private user-library-read user-top-read user-library-modify user-modify-playback-state streaming"
        token = util.prompt_for_user_token(self.username,scope,self.client_id,self.client_secret,redirect_uri)
        self.sp = spotipy.Spotify(auth=token)
        
        #load playlist uris: only save songs that are from these playlists
        with open(playlist_path, 'rb') as f:
            self.playlist_uris = pickle.load(f)
        
        self.recent_path = recent_path
        self.recent = pd.read_csv(recent_path)
        self.recent_backup_path = recent_backup_path
        
        self.last_session_path = last_session_path
        with open(last_session_path, 'rb') as f:
            data = pickle.load(f)
            self.last_timestamp = int(data['timestamp'])
            self.last_session = data['session']
            
        self.all_path = all_path
        self.all_songs = pd.read_csv(all_path, index_col =  'uri')
        self.audio_features = ['danceability', 'energy', 'loudness', 'speechiness', 'acousticness','liveness', 'valence', 'tempo']
        
    def _get_track_info(self, track_dict):
        """
        given Spotify's JSON payload with song's audio features, returns dict
        with song features and whether or not song is new (already in all_songs)
            if new, then retrieves audio features and predicts label
            if not, then copies over audio features + label
        """
        track = track_dict['track']
        
        song_data = dict()

        song_data['artist'] = track['artists'][0]['name']
        song_data['title'] = track['name']
        song_data['played_at'] = datetime.fromisoformat(track_dict['played_at'].replace("T", " ").replace("Z", "")) - timedelta(hours = 4)
        uri = track['uri']
        song_data['uri'] = uri
        
        #true if song already in all_songs df
        new = uri not in self.all_songs.index
        
        #if new, retrieve audio features from API and predict label
        if new:
            af = {k:v for (k,v) in self.sp.audio_features(uri)[0].items() if k in self.audio_features}
            label = predict(list(af.values()))
            
        #if not, then copy over audio features + label
        else:
            row = self.all_songs.loc[uri, :]
            af = dict(row[self.audio_features])
            label = row['label']
        

        #add audio features and label to song_data dictionary
        song_data.update(af)
        song_data['label'] = label

        return song_data, new
        
    def scrape(self, n = 50, save = False):

        #filter out songs not played from specified playlists
        raw_recent = self.sp.current_user_recently_played(limit = n, after = self.last_timestamp)['items'][::-1]
        recent = list(filter(lambda x: x['context']['uri'] in self.playlist_uris, raw_recent))
            
        if len(raw_recent) != 0 and len(recent) == 0:
            most_recent = int(datetime.timestamp(datetime.now())*1000)
            print(f"Last session time: {datetime.fromtimestamp(most_recent/1000).strftime('%m-%d %H:%M %p')}")
            print(f"{len(raw_recent)} songs from untracked playlists played")
            with open(self.last_session_path, 'wb') as f:
                    d = {'timestamp': most_recent, 'session':self.last_session}
                    pickle.dump(d, f)
            print(f"Last session time saved to {self.last_session_path}")
            return
        
        #datetime format
        fmt = "(%m/%d) %H:%M %p"
        n_songs = len(recent)
        
        #load
#         last_session_time = datetime.utcfromtimestamp(self.last_timestamp/1000)
#         prev_time = last_session_time
        prev_time = datetime.utcfromtimestamp(self.last_timestamp/1000)
        
        #if n_songs == 0, then no untracked recent songs
        if n_songs != 0:
            #load previous session id in case new songs played < 20 min after last scrape
            prev_session = self.last_session
            
            #list of dicts of song features
            data = []      
            
            #songs played > 20  min apart are considered separate sessions
            period = timedelta(minutes = 20)
            
            new_songs = []
                
            for track in tqdm(recent):
                row, new = self._get_track_info(track)
                
                if new:
                    #add to list of new songs
                    new_songs.append(f"{row['artist']}: {row['title']}")
                    
                    #update all_songs
                    
                    row_copy = {k:[v] for (k,v) in row.items() if k != 'played_at'}
                    row_copy.update({'pc1':np.nan, 'pc2':np.nan})
                    new_song_df = pd.DataFrame(row_copy, columns = ['uri'] + list(self.all_songs.columns)).set_index('uri')
                    self.all_songs = self.all_songs.append(new_song_df)
                    
                #need time as datetimeobj to check time between songs
                time = row['played_at']
                
                #convert time to specified format for readability in recent df
                str_time = time.strftime(fmt)    
                row['played_at'] = str_time
                  
                #check if elapsed time between this song and previous song > 20 min
                if abs(time - prev_time) > period:
                    #update session id
                    prev_session = hashlib.sha1(str_time.encode('utf-8')).hexdigest()
                    
                row['session'] = prev_session
                
                #update most recent time
                prev_time = time

                data.append(row)

            df = pd.DataFrame(data, columns = self.recent.columns)
            self.data = data
            

            print(f"Songs processed: {n_songs}")
            if len(new_songs) > 0:
                print(f"New songs added to all_songs DataFrame: {new_songs}")
            print(f"Last session time: {prev_time.strftime(fmt)}")
            
            #unix timestamp of last play time
            self.most_recent_timestamp = int(datetime.timestamp(prev_time)*1000)
            
            if save:
                self.recent.to_csv(self.recent_backup_path, index = False) #store old data in backup csv
                self.recent.append(df).to_csv(self.recent_path, index = False) #update old data in recent csv
                with open(self.last_session_path, 'wb') as f:
                    d = {'timestamp': self.most_recent_timestamp, 'session':prev_session}
                    pickle.dump(d, f)
                print(f"Session data saved to {self.recent_path}")
                print(f"Last session time saved to {self.last_session_path}")

            return df
        
        else:
            print(f"No new songs played since {(prev_time-timedelta(hours = 4)).strftime(fmt)}")
            return None

if __name__ == '__main__':
    rs = RecentScraper()
    df = rs.scrape(save = True)