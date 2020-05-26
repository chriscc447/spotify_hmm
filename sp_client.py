import spotipy
import spotipy.util as util

def Spotify_Client():
    with open("ref/api.txt", "r") as f:
        username, client_id, client_secret = [x.strip() for x in f]
    redirect_uri = "http://localhost:8000"
    scope = "playlist-read-private playlist-read-collaborative user-read-recently-played playlist-modify-private user-library-read user-top-read user-library-modify user-modify-playback-state streaming"
    token = util.prompt_for_user_token(username,scope,client_id,client_secret,redirect_uri)
    sp = spotipy.Spotify(auth=token)
    return sp