# ComperStock
ComperStock is a virtual stock game, in which the stocks' values and dividend are tied to a player's performance in the game Counter-Strike: Global Offensive. The game is mainly run through Discord, using the Discord Bot API. MongoDB (hosted by AWS through MongoDB Atlas) is used for data storage. Tracker.gg's CS:GO stats API was used to retrieve player's stats. This project was written entirely in Python.

To run, the program requires a .env file containing a Discord Bot key, a MongoDB connection url, and a Tracker.gg API key.

It's called ComperStock because competitive CS:GO matches are sometimes referred to as "comps", and the people participating in them as "compers".

# Features
- Register your Steam profile to a stock ticker that gives dividends based on your CS:GO performance.
- Sell and buy those stocks in a real-time marketplace.
- Graphs and analytics provided through the Discord bot let you follow patterns and trends in stock and trader performance.
