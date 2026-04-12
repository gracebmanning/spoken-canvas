

# Basic Architecture

* serve.py is the webserver that acts as the central communication hub
* listen.py is a client.  It detects the user's speech, determines current location in the script, and sends commands to the websocket server, which will forward along to other clients as necessary


# Check the setup

Start the web socket server and the listener

```
python listener/serve.py
python listener/listen.py tests/basic_browser_test.script
```

Open `interpreters/browser/paper_and_anime_plaground.html` in your browser (or in OBS).

Read the first line of the script, and a red circle should appear.

