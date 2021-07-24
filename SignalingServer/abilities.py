from pyee import AsyncIOEventEmitter

class BrainRunner(AsyncIOEventEmitter):
    def __init__(self, eventLoop):
        super().__init__(eventLoop)
        print("Created BrainRunner")

    def receiveAudioFrame(self, frame):
        self.emit("audio", frame)

    def receiveVideoFrame(self, frame):
        pass

    def __fireOutputAfterTick(self):
        self.emit("audio", [])