import spotipy
import pandas as pd
from spotipy.oauth2 import SpotifyClientCredentials, SpotifyOAuth
import spotipy.util as util
import pprint
from tqdm.notebook import tqdm
import re
from dateutil.parser import isoparse as dateparse
from datetime import datetime, timedelta
import pickle

pp = pprint.PrettyPrinter(indent=4)

class RecentScraper():
    def __init__(self, redirect_uri = "http://localhost:8000", token_path = "ref/api.txt", recent_path = "data/recent.csv", playlist_path = 'ref/playlists.data', timestamp_path = "data/timestamp.data", all_path = "data/all_songs.csv"):
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
        
        self.timestamp_path = timestamp_path
        with open(timestamp_path, 'rb') as f:
            self.timestamp = pickle.load(f)
        
        self.all_path = all_path
        self.all_songs = pd.read_csv(all_path)
        
    def _get_track_info(self, track_dict):
        track = track_dict['track']

        name = track['name']
        artist = track['artists'][0]['name']
        uri = track['uri']
        time = datetime.fromisoformat(track_dict['played_at'].replace("T", " ").replace("Z", "")) - timedelta(hours = 4)

        return artist, name, time, uri
        
    def scrape(self, n = 50, save = False):

        recent = self.sp.current_user_recently_played(limit = n, after = self.timestamp)['items']
        recent = list(filter(lambda x: x['context']['uri'] in self.playlist_uris, recent))        

        fmt = "(%m/%d) %H:%M %p"
        n_songs = len(recent)
        if n_songs != 0:
            bar = tqdm(total = n_songs)

            cols = ['artist', 'title', 'played_at', 'session', 'uri']
            row_skel = {c:None for c in cols}
            data = []      #list of dicts of audio features
            ref = dict()   #query:index in data
            period = timedelta(minutes = 20)

            #process first song
            row = row_skel.copy()
            artist, name, time, uri = self._get_track_info(recent[0])
            str_time = time.strftime(fmt)
                
            most_recent = int(datetime.timestamp(time)*1000)


            row['artist'] = artist
            row['title'] = name
            row['played_at'] = str_time
            row['session'] = hash(str_time)
            row['uri'] = uri

            prev_time = time
            prev_session = row['session']

            data.append(row)
            ref[uri] = len(data)-1
            
            bar.update(1)


            #process rest of songs
            for track in recent[1:]:
                artist, name, time, uri = self._get_track_info(track)
                str_time = time.strftime(fmt)

                if uri not in ref:
                    row = row_skel.copy()
                    row['artist'] = artist
                    row['title'] = name            
                    row['played_at'] = str_time
                    row['uri'] = uri

                    if abs(time - prev_time) > period:
                        prev_session = hash(str_time)
                    row['session'] = prev_session

                    data.append(row)
                    ref[uri] = len(data)-1

                else:
                    row = data[ref[uri]].copy()
                    row['played_at'] = str_time
                    if abs(time - prev_time) > period:
                        prev_session = hash(str_time)
                    row['session'] = prev_session
                    data.append(row) 
                    
                prev_time = time
                bar.update(1)
            bar.close()

            df = pd.DataFrame(data, columns = cols)
            
            
            self.data = data
            self.ref = ref
            self.most_recent = most_recent
            print(f"Songs processed: {n_songs}")
            print(f"Last session time: {datetime.fromtimestamp(most_recent/1000).strftime('%m-%d %H:%M %p')}")
            if save:
                df.append(self.recent).to_csv(self.recent_path, index = False)
                with open(self.timestamp_path, 'wb') as f:
                    pickle.dump(most_recent, f)
                print(f"Session data saved to {self.recent_path}")
                print(f"Last session time saved to {self.timestamp_path}")

            return df
        
        else:
            print(f"No new songs played since {datetime.fromtimestamp(self.timestamp/1000).strftime('%m-%d %H:%M %p')}")
            return None

if __name__ == '__main__':
    rs = RecentScraper()
    df = rs.scrape(save = True)