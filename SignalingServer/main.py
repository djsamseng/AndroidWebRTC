import asyncio
# pip install python-engineio==3.14.2 python-socketio[asyncio_client]==4.6.0

import socketio

import aiohttp
import cv2

import av
from aiortc import RTCPeerConnection,\
    RTCSessionDescription,\
    VideoStreamTrack,\
    RTCIceCandidate,\
    RTCIceGatherer,\
    RTCIceServer,\
    sdp,\
    MediaStreamTrack
from aiortc.contrib.media import MediaPlayer, MediaRecorder

import abilities

import numba
from numba import cuda
import numpy as np
import os
import time
from mpi4py import MPI

import matplotlib.pyplot as plt

import pyaudio

sio = socketio.AsyncClient()

## GLOBALS
pc = None
isInitiator = False
player = None
p_stream = None
audio_replay_track = None

class AudioReplayTrack(MediaStreamTrack):
    kind = "audio"
    def __init__(self):
        super().__init__()
        self.dataQueue = asyncio.Queue()
        self.itr = 0

    async def recv(self):
        try:
            data = await self.dataQueue.get()
            audio_array = np.zeros((1, 1920), dtype='int16')
            audio_array[:,:] = data["data"][:,:]

            frame = av.AudioFrame.from_ndarray(audio_array, 's16')
            frame.sample_rate = 48000
            frame.time_base = '1/48000'
            frame.pts = data["pts"]
            self.itr += 960 # TODO: Correctly increment base

            return frame
        except Exception as e:
            print("AudioReplayTrack recv was called with Exception:", e)

    def addFrame(self, frame):
        self.dataQueue.put_nowait(frame)

    def stop(self):
        try:
            super().stop()
            print("AudioReplayTrack stop was called")
        except Exception as e:
            print("AudioReplayTrack stop was called with exception:", e)


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
        await addTracks()
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

async def createPeerConnection():
    global pc
    p = pyaudio.PyAudio()
    p_stream = None
    if pc:
        raise Exception("RTCPeerConnection alread established")

    pc = RTCPeerConnection()

    @pc.on("track")
    async def on_track(track):
        global p_stream
        print("Received track:", track.kind)
        if track.kind == "audio":
            while True:
                try:
                    frame = await track.recv()

                    if not p_stream:
                        assert frame.format.bits == 16
                        assert frame.sample_rate == 48000
                        assert frame.layout.name == "stereo"
                        p_stream = p.open(format=pyaudio.paInt16,
                            channels=2,
                            rate=48000,
                            output=True)

                    as_np = frame.to_ndarray()
                    audio_replay_track.addFrame({
                        "data": as_np,
                        "pts": frame.pts
                    })
                    as_np = as_np.astype(np.int16).tostring()
                    p_stream.write(as_np)

                except Exception as e:
                    print("Error receiving audio:", e)

        if track.kind == "video":
            while True:
                try:
                    t1 = time.time()
                    frame = await track.recv()
                    t2 = time.time()
                    img = frame.to_rgb().to_ndarray()
                    t3 = time.time()
                    img_gpu = cuda.to_device(img)
                    t4 = time.time()
                    MPI.COMM_WORLD.send(img_gpu.get_ipc_handle(), dest=1)
                    t5 = time.time()
                    #print("Recv:", t2 - t1, " to_ndarray", t3 - t2,
                    #    " to_device:", t4 - t3,
                    #    " send:", t5-t4)
                except Exception as e:
                    print("Error receiving track", e)

    @pc.on("connectionstatechange")
    def on_connectionstatechange():
        print("connectionstatechange:", pc.connectionState)

async def addTracks():
    global player
    global audio_replay_track
    if player:
        if player.video:
            player.video.stop()
        if player.audio:
            player.audio.stop()

    player = MediaPlayer('/dev/video0', format='v4l2', options={
        'video_size': '320x240'
    })
    add_player(pc, player)

    audio_replay_track = AudioReplayTrack()
    pc.addTrack(audio_replay_track)

    print("Created peer")

async def createOffer():
    if not isInitiator:
        return
        # raise Exception("Should createOffer only when the initiator")

    await addTracks()
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


async def main(brain):
    @brain.on("audio")
    def output_audio(frame):
        print("Output audio:", frame)

    brain.receiveAudioFrame([123])

    await sio.connect("http://192.168.1.220:3000")
    print("My sid:", sio.sid)
    room = "foo"
    await sio.emit("create or join", room)
    await createPeerConnection()
    await sendMessage("got user media")
    await sio.wait()

async def close():
    await asyncio.sleep(0.1)

def rank0():
    loop = asyncio.get_event_loop()
    brain = abilities.BrainRunner(loop)
    try:
        loop.run_until_complete(
            main(brain)
        )
    except KeyboardInterrupt as e:
        print("Keyboard Interrupt")
    finally:
        print("Cleaning up")
        loop.run_until_complete(
            close()
        )

        print("Exiting")


# mpirun -np 2 python3 main.py
if __name__ == "__main__":
    rank = MPI.COMM_WORLD.Get_rank()
    if rank == 0:
        rank0()
    elif rank == 1:
        didShow = False
        while True:
            t1 = time.time()
            handle = MPI.COMM_WORLD.recv(source=0)
            try:
                t2 = time.time()
                gpu_input = handle.open().copy_to_host()
                cv2.imshow("test", gpu_input)
                cv2.waitKey(5)
                t3 = time.time()
                #print("Rank 1: recv:", t2-t1, " open:", t3-t2, flush=True)
            except Exception as e:
                print("Rank 1: Failed to handle", e)
