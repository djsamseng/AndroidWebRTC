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
        await createOffer()
    if data and "type" in data and data["type"] == "offer":
        await pc.setRemoteDescription(
            RTCSessionDescription(
                sdp=data["sdp"], type=data["type"]
            )
        )
        localDesc = await pc.createAnswer()
        await pc.setLocalDescription(localDesc)
        await sendMessage({
            "sdp": localDesc.sdp,
            "type": localDesc.type
        })
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
player = None
async def createPeerConnection():
    global pc
    global player
    if pc:
        raise Exception("RTCPeerConnection alread established")

    pc = RTCPeerConnection()
    if player:
        if player.video:
            player.video.stop()
        if player.audio:
            player.audio.stop()

    player = MediaPlayer('/dev/video0', format='v4l2', options={
        'video_size': '320x240'
    })
    add_player(pc, player)

    @pc.on("track")
    async def on_track(track):
        print("Received track", track)

    print("Created peer")

async def createOffer():
    if not isInitiator:
        raise Exception("Should createOffer only when the initiator")

    print("isInitiator: creating offer")
    desc = await pc.createOffer()
    print("Created local description")
    await pc.setLocalDescription(desc)
    await sendMessage({
        "sdp": desc.sdp,
        "type": desc.type
    })

async def cleanup():
    global pc
    await pc.close()
    pc = None

@sio.on("created")
async def on_created(data, *args):
    global isInitiator
    print("Received on_created", data, args)
    isInitiator = True

@sio.on("isinitiator")
async def on_isinitiator(room):
    global isInitiator
    global pc
    print("Received isInitiator", room)
    isInitiator = True
    await cleanup()
    await createPeerConnection()

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
    await createPeerConnection()
    await sendMessage("got user media")
    await sio.wait()

async def close():
    await asyncio.sleep(0.1)

if __name__ == "__main__":
    loop = asyncio.get_event_loop()
    try:
        loop.run_until_complete(
            main()
        )
    except KeyboardInterrupt as e:
        print("Keyboard Interrupt")
    finally:
        print("Cleaning up")
        loop.run_until_complete(
            close()
        )

        print("Exiting")