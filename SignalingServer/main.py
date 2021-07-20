import asyncio
# pip install python-engineio==3.14.2 python-socketio[asyncio_client]==4.6.0

import socketio

import aiohttp

from aiortc import RTCPeerConnection,\
    RTCSessionDescription,\
    VideoStreamTrack,\
    RTCIceCandidate,\
    RTCIceGatherer,\
    RTCIceServer,\
    sdp
from aiortc.contrib.media import MediaPlayer, MediaRecorder

sio = socketio.AsyncClient()

pc = None

async def sendMessage(msg):
    await sio.emit("message", msg)

@sio.event
async def message(data):
    print("Received message")

@sio.on("message")
async def on_message(data):
    print("Received on_message", data)
    if data == "got user media":
        print("INITIATING!")
        await createPeerConnection()
    if data and "type" in data and data["type"] == "offer":
        # await createPeerConnection(data)
        print("OFFER NOT CREATING")
    elif data and "type" in data and data["type"] == "answer":
        await pc.setRemoteDescription(
            RTCSessionDescription(
                sdp=data["sdp"], type=data["type"]
            )
        )
    elif data and "type" in data and data["type"] == "candidate":
        print("Got candidate:", data)
        can = sdp.candidate_from_sdp(data["candidate"])
        can.sdpMid = data["id"]
        can.sdMLineIndex = data["label"]
        await pc.addIceCandidate(can)
        '''
        can = RTCIceCandidate(
            sdpMLineIndex=data["label"], sdpMid=data["id"]
        )
        pc.addRemoteCandidate(can)
        '''

def add_player(pc, player):
    if player.audio:
        print("Adding audio")
        pc.addTrack(player.audio)
    if player.video:
        print("Adding video")
        pc.addTrack(player.video)

isInitiator = False
async def createPeerConnection():
    global pc
    pc = RTCPeerConnection()

    '''
    iceServers = [
        RTCIceServer(urls="stun:stun.l.google.com:19302")
    ]
    gatherer = RTCIceGatherer(iceServers)
    await gatherer.gather()
    print("LOCAL CANDIDATES:", gatherer.getLocalCandidates())
    '''

    filename = "/home/samuel/Downloads/examples_server_demo-instruct.wav"
    player = MediaPlayer(filename)
    #add_player(pc, player)
    player = MediaPlayer('/dev/video0', format='v4l2', options={
        'video_size': '320x240'
    })
    add_player(pc, player)

    @pc.on("track")
    async def on_track(track):
        print("Received track", track)



    #transceiver = pc.addTransceiver("recvonly")

    #pc.addTrack(VideoStreamTrack())

    print("Created peer")

    if isInitiator:
        print("IS INITIATOR!!!!!")
        desc = await pc.createOffer()
        print("Created local description:", desc)
        await pc.setLocalDescription(desc)
        await sendMessage({
            "sdp": desc.sdp,
            "type": desc.type
        })

@sio.on("created")
async def on_created(data, *args):
    global isInitiator
    print("Received on_created", data, args)
    isInitiator = True

@sio.on("full")
async def on_full(data):
    print("Received on_full", data)

@sio.on("join")
async def on_join(data):
    print("Received on_join", data)

@sio.on("joined")
async def on_joined(room, socket_id):
    print("Received on_joined", room, socket_id)

@sio.on("log")
async def on_log(data):
    print("Received on_log", data)





async def main():
    await sio.connect("http://192.168.1.220:3000")
    print("My sid:", sio.sid)
    room = "foo"
    await sio.emit("create or join", room)
    await sendMessage("got user media")
    await sio.wait()

if __name__ == "__main__":
    loop = asyncio.get_event_loop()
    try:
        loop.run_until_complete(
            main()
        )
    except KeyboardInterrupt:
        print("Keyboard Interrupt")
    finally:
        print("Exiting")