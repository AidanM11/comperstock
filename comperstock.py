import discord
import requests
import json
import pymongo
import asyncio
import os
from datetime import datetime
import matplotlib.pyplot as plt
from dotenv import load_dotenv

load_dotenv()

def apiGetKills(steamID):
    headers = {'TRN-Api-Key': os.getenv('TRCKRKEY'), 'Accept': 'application/json', 'Accept-Encoding': 'gzip'}
    api_url = 'https://public-api.tracker.gg/v2/csgo/standard/profile/steam/' + steamID
    response = requests.get(api_url, headers=headers)
    if(response.status_code != 200):
        return -1
    numKills = response.json()["data"]["segments"][0]["stats"]["kills"]["value"]
    return numKills

STARTING_MONEY = 50000
STARTING_STOCKS = 1000

mongoClient = pymongo.MongoClient(os.getenv('MONGOCONNECT'))
marketDB = mongoClient["marketDB1"]
tickers = marketDB["tickers"]
traders = marketDB["traders"]
listings = marketDB["listings"]
prevSales = marketDB["prevSales"]
prevDiv = marketDB["prevDividends"]
holdings = marketDB["holdings"]
mesQueue = []
client = discord.Client()

#Return codes: 
# 0 - Operation successful
# 1 - Ticker name in use
# 2 - Ticker steamID in use
# 3 - Ticker discID in use
# 4 - SteamID stats could not be accessed
# 5 - User is not registered
def createTicker(name, steamID, discID):
    name = name.upper()
    query = {"name": name}
    if tickers.count_documents(query) > 0:
        return 1
    query = {"steamID": steamID}
    if tickers.count_documents(query) > 0:
        return 2
    query = {"discID": discID}
    if tickers.count_documents(query) > 0:
        return 3
    currKills = apiGetKills(steamID)
    if currKills == -1:
        return 4
    query = {"discID": discID}
    if traders.count_documents(query) < 1:
        return 5
    
    newTicker = {"name": name, "steamID": steamID, "discID": discID, "currKills": currKills}
    tickers.insert_one(newTicker)
    newHolding = {"discID": discID, "ticker": name, "num": STARTING_STOCKS}
    holdings.insert_one(newHolding)
    return 0

#Return codes
# 0 - successful
# 1 - User already registered
def createTrader(discID):
    query = {"discID": discID}
    if traders.count_documents(query) > 0 :
        return 1
    newTrader = {"discID": discID, "money": STARTING_MONEY}
    traders.insert_one(newTrader)
    return 0

#Return codes
# 0 - successful
# 1 - user does not exist
# 2 - ticker does not exist
# 3 - user does not have enough stock
# 4 - price is invalid  
# 5 - num is invalid   
def listOnMarket(discID, ticker, num, price):
    num = int(num)
    price = int(price)
    if num <= 0:
        return 5
    if price <= 0:
        return 4
    query = {"discID": discID}
    if traders.count_documents(query) < 1:
        return 1
    query = {"name": ticker}
    if tickers.count_documents(query) < 1:
        return 2
    query = {"discID": discID, "ticker": ticker}
    userHolds = holdings.find(query)
    if holdings.count_documents(query) == 0:
        return 3
    elif userHolds[0]["num"] < num:
        return 3
    if holdings.count_documents(query) > 1:
        print("MAJOR ERROR: multiple holdings for same user and ticker")
    numStocks = userHolds[0]["num"]
    updateVals = {"$set": {"num": numStocks - num}}
    holdings.update_one(query, updateVals)
    newListing = {"seller": discID, "num": num, "price": price, "ticker": ticker}
    listings.insert_one(newListing)
    return 0


#Return codes
# dict[num, moneySpent] - Successful
# 1 - User not registered
# 2 - user does not have enough money
# 3 - ticker does not exist
def buyMaxWith(discID, moneyToSpend, ticker, maxPrice):
    moneyToSpend = int(moneyToSpend)
    maxPrice = int(maxPrice)
    query = {"discID": discID}
    userList = traders.find(query)
    if traders.count_documents(query) < 1:
        return 1
    user = userList[0]
    if user["money"] < moneyToSpend:
        return 2
    query = {"name": ticker}
    if tickers.count_documents(query) < 1:
        return 3
    query = {"ticker": ticker}
    availListings = listings.find(query).sort("price")
    numBought =  0
    moneyLeft = moneyToSpend
    currPrice = -1
    endLoop = False
    for l in availListings:
        if l["price"] > maxPrice:
            break
        canAffordOfThisListing = 0
        moneySpent = 0
        for x in range(1, l["num"] + 1):
            if l["price"] + moneySpent <= moneyLeft:
                canAffordOfThisListing += 1
                moneySpent += l["price"]
                currPrice = l["price"]
            else:
                query = {"_id": l["_id"]}
                newVals = {"$set": {"num": l["num"] - canAffordOfThisListing}}
                listings.update_one(query, newVals)
                numBought += canAffordOfThisListing
                moneyLeft -= moneySpent
                query = {"discID": l["seller"]}
                prevSellersMoney = traders.find_one(query)["money"]
                newVals = {"$set": {"money": prevSellersMoney + moneySpent}}
                traders.update_one(query, newVals)
                endLoop = True
                break
        if endLoop:
            break
        numBought += l["num"]
        moneyLeft -= l["num"] * l["price"]
        currPrice = l["price"]
        query = {"discID": l["seller"]}
        prevSellersMoney = traders.find_one(query)["money"]
        sellersNewMoney = prevSellersMoney + (l["num"] * l["price"])
        print(sellersNewMoney)
        newVals = {"$set": {"money": sellersNewMoney}}
        traders.update_one(query, newVals)
        query = {"_id": l["_id"]}
        listings.delete_one(query)
    query = {"discID": discID}
    user = traders.find_one(query)
    newMoney = user["money"] - moneyToSpend + moneyLeft
    newVals = {"$set": {"money": newMoney}}
    traders.update_one(query, newVals)
    #update trader's holdings
    query = {"discID": discID, "ticker": ticker}
    holds = holdings.find(query)
    if holdings.count_documents(query):
        prevHolds = holds[0]["num"]
        newVals = {"$set": {"num": numBought + prevHolds}}
        holdings.update_one(query, newVals)
    else:
        newHold = {"discID": discID, "ticker": ticker, "num": numBought}
        holdings.insert_one(newHold)
    if holdings.count_documents(query) > 1:
        print("MAJOR ERROR: multiple holdings for same user and ticker")
    if currPrice > 0:
        query = {"name": ticker}
        newVals = {"$set": {"currPrice": currPrice}}
        tickers.update_one(query, newVals)
        newSale = {"ticker": ticker, "price": currPrice, "time": datetime.today()}
        prevSales.insert_one(newSale)
    return {"num": numBought, "moneySpent": moneyToSpend - moneyLeft}

    #returns list of dicts with ticker names and their returns
def fulfillDividends():
    tickerList = tickers.find()
    tickerPerformance = []
    for tick in tickerList:
        name = tick["name"]
        prevKills = tick["currKills"]
        newKills = apiGetKills(tick["steamID"])
        if newKills == -1:
            #Maybe send message saying stats could not be accessed for this ticker?
            tickerPerformance.append({"name": name, "return": -1})
            continue
        dividend = newKills - prevKills
        tickerPerformance.append({"name": name, "return": dividend})
        newDiv = {"ticker": name, "dividend": dividend, "time": datetime.today()}
        prevDiv.insert_one(newDiv)
        query = {"name": name}
        newVals = {"$set": {"currKills": newKills}}
        tickers.update_one(query, newVals)
        if dividend == 0:
            continue
        query = {"ticker": name}
        relevHolds = holdings.find(query)
        for hold in relevHolds:
            earning = hold["num"] * dividend
            query = {"discID": hold["discID"]}
            user = traders.find_one(query)
            newMoney = earning + user["money"]
            newVals = {"$set": {"money": newMoney}}
            traders.update_one(query, newVals)
    tickPerfStr = ""
    for t in tickerPerformance:
        tickPerfStr = tickPerfStr + t["name"] + ": " + str(t["return"]) + "\n"
    return tickPerfStr

#returns 1 if user does not exist, otherwise returns a list of holding objects
def getHoldings(discID):
    query = {"discID": discID}
    if traders.count_documents(query) < 1:
        return 1
    userHolds = holdings.find(query).sort("num")
    return userHolds

def getBalance(discID):
    query = {"discID": discID}
    if traders.count_documents(query) < 1:
        return 1
    user = traders.find_one(query)
    money = user["money"]
    return money

def getLatestPrice(ticker): 
    query = {"name": ticker}
    if tickers.count_documents(query) < 1:
        return 1
    return tickers.find_one(query)["currPrice"]

def getListings(ticker): 
    query = {"ticker": ticker}
    return listings.find(query).sort("price")

def getGraphSales(ticker):
    query = {"ticker": ticker}
    if prevSales.count_documents(query) < 1:
        return 1
    dateData = []
    priceData = []
    salesList = prevSales.find(query)
    for sale in salesList:
        dateData.append(sale["time"])
        priceData.append(sale["price"])
    graph = plt.plot(dateData, priceData)
    plt.gcf().autofmt_xdate()
    plt.title("Price of $" + ticker)
    plt.savefig("graph.png")
    plt.clf()
    return "SENDIMG"

def getGraphDividend(ticker):
    query = {"ticker": ticker}
    if prevDiv.count_documents(query) < 1:
        return 1
    dateData = []
    divData = []
    divList = prevDiv.find(query)
    for div in divList:
        dateData.append(div["time"])
        divData.append(div["dividend"])
    graph = plt.plot(dateData, divData)
    plt.gcf().autofmt_xdate()
    plt.title("Dividend History of $" + ticker)
    plt.savefig("graph.png")
    plt.clf()
    return "SENDIMG"

def parseMessage(message, user):
    messParts = message.split()
    cmd = messParts[0]
    if cmd == "!CREATETICKER":
        if len(messParts) != 3 or not isinstance(messParts[1], str) or not isinstance(messParts[2], str) or len(messParts[2]) > 4:
            return "Usage: !createticker <steamID> <tickerName> (ticker name must be <5 chars)"
        code = createTicker(messParts[2], messParts[1], user)
        # 0 - Operation successful
        # 1 - Ticker name in use
        # 2 - Ticker steamID in use
        # 3 - Ticker discID in use
        # 4 - SteamID stats could not be accessed
        # 5 - User is not registered
        if code == 0:
            return "Successfully created ticker $" + messParts[2] + " with steamID " + messParts[1] + "."
        elif code == 1:
            return "Ticker name is already in use!"
        elif code == 2:
            return "That SteamID already has a ticker!"
        elif code == 3:
            return "You have already created your ticker!"
        elif code == 4:
            return "That SteamID's stats could not be accessed. Either that is not a real SteamID, that accounts stats are private, or the API is down"
        elif code == 5:
            return "You have not registered yet. Please use !register to create your ComperStock account."
    if cmd == "!REGISTER":
        if len(messParts) != 1:
            return "Usage: !register"
        code = createTrader(user)
        if code == 0:
            return "Succesfully registered!"
        elif code == 1:
            return "You have already registered!"
    if cmd == "!LIST":
        if len(messParts) != 4 or not messParts[2].isdigit() or not messParts[2].isdigit():
            return "Usage: !list <ticker> <numStocksToList> <price>"

        code = listOnMarket(user, messParts[1], messParts[2], messParts[3])
        # 0 - successful
        # 1 - user does not exist
        # 2 - ticker does not exist
        # 3 - user does not have enough stock
        # 4 - price is invalid  
        # 5 - num is invalid   
        if code == 0:
            return "Succesfully listed " + messParts[2] + " $" + messParts[1] + " at $" + messParts[3] + " each."
        elif code == 1: 
            return "You have not registered yet. Please use !register to create your ComperStock account."
        elif code == 2: 
            return "That ticker does not exist."
        elif code == 3:
            return "You do not own enough $" + messParts[1] + " to make this transaction."
        elif code == 4:
            return "Not a valid price."
        elif code == 5:
            return "Not a valid number of stocks."
    if cmd == "!BUYMAXWITH":
        if len(messParts) != 4 or not messParts[2].isdigit() or not messParts[2].isdigit():
            return "Usage: !buyMaxWith <ticker> <moneyToSpend> <maxPrice>"
        code = buyMaxWith(user, messParts[2], messParts[1], messParts[3])
        # dict[num, moneySpent] - Successful
        # 1 - User not registered
        # 2 - user does not have enough money
        # 3 - ticker does not exist
        if code == 1:
            return "You have not registered yet. Please use !register to create your ComperStock account."
        elif code == 2:
            return "You do not have enough money to complete this transaction."
        elif code == 3:
            return "That ticker does not exist."
        else:
            return "Bought " + str(code["num"]) + " shares of $" + messParts[1] + " for a total of $" + str(code["moneySpent"]) + "."
    if cmd == "!MYHOLDINGS":
        if len(messParts) != 1:
            return "Usage: !myholdings"
        code = getHoldings(user)
        if code == 1:
            return "You have not registered yet. Please use !register to create your ComperStock account."
        else:
            result = "Your Holdings: \n"
            for hold in code:
                result = result + "$" + hold["ticker"] + ": " + str(hold["num"]) + "\n"
            return result
    if cmd == "!BALANCE":
        if len(messParts) != 1:
            return "Usage: !balance"
        code = getBalance(user)
        if code == 1:
            return "You have not registered yet. Please use !register to create your ComperStock account."
        else:
            return "Balance: " + str(code)
    if cmd == "!LISTINGS":
        if len(messParts) != 2:
            return "Usage: !listings <ticker>"
        code = getListings(messParts[1])
        result = "Listings of $" + str(messParts[1]) + ":\n"
        for l in code:
            result = result + str(l["num"]) + " of $" + messParts[1] + " at $" + str(l["price"]) + "\n"
        return result
    if cmd == "!GETLATESTPRICE":
        if len(messParts) != 2:
            return "Usage: !getLatestPrice <ticker>"
        code = getLatestPrice(messParts[1])
        if code == 1:
            return "That ticker does not exist."
        else:
            return "Latest price of $" + messParts[1] + ": " + str(code)
    if cmd == "!GETSALESGRAPH":
        if len(messParts) != 2:
            return "Usage: !getSalesGraph <ticker>"
        code = getGraphSales(messParts[1])
        if code == 1:
            return "That ticker has no sales history."
        else:
            return "SENDIMG"
    if cmd == "!GETPERFORMANCEGRAPH":
        if len(messParts) != 2:
            return "Usage: !getPerformanceGraph <ticker>"
        code = getGraphDividend(messParts[1])
        if code == 1:
            return "That ticker has no performance history."
        else:
            return "SENDIMG"

    



@client.event
async def on_ready():
    print('We have logged in as {0.user}'.format(client))

@client.event
async def on_message(message):
    if message.author == client.user:
        return

    if message.content.startswith('!'):
        mesQueue.append(message)
        #newMes = parseMessage(message.content, message.author.id)
        #await message.channel.send(newMes)

async def comperStockLogic():
    currDay = datetime.today().date()
    while True:
        if len(mesQueue) != 0:
            newMes = mesQueue.pop()
            print("message received: " + newMes.content)
            answerContent = parseMessage(newMes.content.upper(), newMes.author.id)
            if answerContent == None:
                continue
            if answerContent == "SENDIMG":
                await newMes.channel.send(file=discord.File('graph.png'))
            else:
                answerMes = newMes.author.mention + " " + answerContent
                await newMes.channel.send(answerMes)
        if currDay != datetime.today().date():
            currDay = datetime.today().date()
            updateMes = "Dividends have been distributed, they are as follows:\n" + fulfillDividends()
            for guild in client.guilds:
                for channel in guild.text_channels:
                    if channel.name == "comperstock":
                        await channel.send(updateMes)

        await asyncio.sleep(1)

client.loop.create_task(comperStockLogic())
client.run(os.getenv('DISCORD_TOKEN'))
