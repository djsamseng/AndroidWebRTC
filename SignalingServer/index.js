'use strict';

var os = require('os');
var nodeStatic = require('node-static');
var http = require('http');
var socketIO = require('socket.io');
const port = process.env.PORT || 3000;

var fileServer = new(nodeStatic.Server)();
var app = http.createServer(function(req, res) {
  fileServer.serve(req, res);
}).listen(port);

var io = socketIO.listen(app);
io.sockets.on('connection', function(socket) {
  console.log("Got connection")
  // convenience function to log server messages on the client
  function log() {
    var array = ['Message from server:'];
    array.push.apply(array, arguments);
    socket.emit('log', array);
  }

  socket.on('message', function(message) {
    console.log('message')
    log('Client said: ', message);
    // for a real app, would be room-only (not broadcast)
    socket.broadcast.emit('message', message);
  });

  socket.on('create or join', function(room) {
    console.log('create or join')
    log('Received request to create or join room ' + room);

    var clientsInRoom = io.sockets.adapter.rooms[room];
    var numClients = clientsInRoom ? Object.keys(clientsInRoom.sockets).length : 0;
    log('Room ' + room + ' now has ' + numClients + ' client(s)');
    console.log('Room ' + room + ' now has ' + numClients + ' client(s)');

    if (numClients === 0) {
      socket.join(room);
      log('Client ID ' + socket.id + ' created room ' + room);
      socket.emit('created', room, socket.id);

    } else {
      log('Client ID ' + socket.id + ' joined room ' + room);
      io.sockets.in(room).emit('join', room);
      socket.join(room);
      socket.emit('joined', room, socket.id);
      io.sockets.in(room).emit('ready');
    }
  });

  socket.on('ipaddr', function() {
    console.log("ipaddr")
    var ifaces = os.networkInterfaces();
    for (var dev in ifaces) {
      ifaces[dev].forEach(function(details) {
        if (details.family === 'IPv4' && details.address !== '127.0.0.1') {
          socket.emit('ipaddr', details.address);
        }
      });
    }
  });

  socket.on('bye', function(){
    console.log('received bye from');
  });

  socket.on('disconnecting', () => {
    for (const roomName of Object.keys(socket.rooms)) {
      if (roomName !== socket.id) {
        const room = io.sockets.adapter.rooms[roomName];
        const numRemainingClients = Object.keys(room.sockets).length - 1;
        if (numRemainingClients === 1) {
          console.log("Sending isInitiator");
          io.sockets.in(roomName).emit('isinitiator', roomName);
        }
        console.log(
          "Room:",
          roomName,
          "will now have",
          Object.keys(room.sockets).length - 1,
          "clients left");
      }
    }
  })

  socket.on('disconnect', function(){
    console.log('Received disconnect from:', socket.id);
  })

});

console.log("Socket io listening")
