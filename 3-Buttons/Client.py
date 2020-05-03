from tkinter import *
import tkinter.messagebox
from PIL import Image, ImageTk
import socket, threading, sys, traceback, os
from time import time
 
from RtpPacket import RtpPacket
 
CACHE_FILE_NAME = "cache-"
CACHE_FILE_EXT = ".jpg"
 
class Client:
    INIT = 0
    READY = 1
    PLAYING = 2
    state = INIT
    
    SETUP = 0
    PLAY = 1
    PAUSE = 2
    TEARDOWN = 3

    NUM_LOST_PACKETS = 0
    NUM_RECV_PACKETS = 0
    
    # Initiation..
    def __init__(self, master, serveraddr, serverport, rtpport, filename):
        self.master = master
        self.master.protocol("WM_DELETE_WINDOW", self.handler)
        self.createWidgets()
        self.serverAddr = serveraddr
        self.serverPort = int(serverport)
        self.rtpPort = int(rtpport)
        self.fileName = filename
        self.rtspSeq = 0
        self.sessionId = 0
        self.requestSent = -1
        self.teardownAcked = 0
        self.connectToServer()
        self.frameNbr = 0.
        self.playTime = 0.0
    
        #Added to initialize setup
        if self.state == self.INIT:
            self.sendRtspRequest(self.SETUP)
            print('setup initialized')

        
    def createWidgets(self):
        """Build GUI."""
        # Create Setup button
        #self.setup = Button(self.master, width=20, padx=3, pady=3)
        #self.setup["text"] = "Setup"
        #self.setup["command"] = self.setupMovie
        #self.setup.grid(row=1, column=0, padx=2, pady=2)
        
        # Create Play button        
        self.start = Button(self.master, width=20, padx=3, pady=3)
        self.start["text"] = "Play"
        self.start["command"] = self.playMovie
        self.start.grid(row=1, column=1, padx=2, pady=2)
        
        # Create Pause button           
        self.pause = Button(self.master, width=20, padx=3, pady=3)
        self.pause["text"] = "Pause"
        self.pause["command"] = self.pauseMovie
        self.pause.grid(row=1, column=2, padx=2, pady=2)
        
        # Create Teardown button
        self.teardown = Button(self.master, width=20, padx=3, pady=3)
        self.teardown["text"] = "Teardown"
        self.teardown["command"] =  self.exitClient
        self.teardown.grid(row=1, column=3, padx=2, pady=2)
        
        # Create a label to display the movie
        self.label = Label(self.master, height=19)
        self.label.grid(row=0, column=0, columnspan=4, sticky=W+E+N+S, padx=5, pady=5) 
    
    #def setupMovie(self):
    #    """Setup button handler."""
    #    if self.state == self.INIT:
    #``        self.sendRtspRequest(self.SETUP)
    
    def exitClient(self):
        """Teardown button handler."""
        self.sendRtspRequest(self.TEARDOWN)     
        self.master.destroy() # Close the gui window
        os.remove(CACHE_FILE_NAME + str(self.sessionId) + CACHE_FILE_EXT) # Delete the cache image from video
 
    def pauseMovie(self):
        """Pause button handler."""
        if self.state == self.PLAYING:
            self.sendRtspRequest(self.PAUSE)
    
    def playMovie(self):
        """Play button handler."""
        if self.state == self.READY:
            # Create a new thread to listen for RTP packets
            threading.Thread(target=self.listenRtp).start()
            self.playEvent = threading.Event()
            self.playEvent.clear()
            self.sendRtspRequest(self.PLAY)
    
    def listenRtp(self):        
        """Listen for RTP packets."""
        total_bytes_sent = 0
        start_time = time()
        elapsed_time = 0.0
        while True:
            try:
                data = self.rtpSocket.recv(20480)
                if data:
                    rtpPacket = RtpPacket()
                    rtpPacket.decode(data)
                    bytes_sent = sys.getsizeof(data)
                    total_bytes_sent = bytes_sent + total_bytes_sent

                    currFrameNbr = rtpPacket.seqNum()
                    end_time = time()
                    elapsed_time = end_time - start_time
                    real_playtime = elapsed_time + self.playTime
                    video_data_rate = total_bytes_sent / real_playtime
                    print("\nCurrent Seq Num: " + str(currFrameNbr))          
                    #print("\nBytes sent: " + str(bytes_sent))    
                    #print("Total Bytes sent: " + str(total_bytes_sent))       
                    #print("PlayTime: " + str(self.playTime))    
                    #print("Elapsed Time: " + str(elapsed_time))
                    print("PlayTime: " + str(real_playtime)) 
                    print("Video Date Rate: " + str(video_data_rate) + " total bytes/sec") 
                    
                    if currFrameNbr - self.frameNbr > 1: #dropped packet
                        self.NUM_LOST_PACKETS = self.NUM_LOST_PACKETS + 1
                        self.frameNbr = currFrameNbr
                        self.updateMovie(self.writeFrame(rtpPacket.getPayload()))  

                    elif currFrameNbr > self.frameNbr: # Discard the late packet
                        self.NUM_RECV_PACKETS = self.NUM_RECV_PACKETS + 1
                        self.frameNbr = currFrameNbr
                        self.updateMovie(self.writeFrame(rtpPacket.getPayload()))

                    # print statistics
                    print("NUM_LOST_PACKETS: ", self.NUM_LOST_PACKETS)
                    print("NUM_RECV_PACKETS: ", self.NUM_RECV_PACKETS)
                    print("PACKET LOSS RATE: ", 100 * self.NUM_LOST_PACKETS/(self.NUM_LOST_PACKETS + self.NUM_RECV_PACKETS), "%")

            except:
                # Stop listening upon requesting PAUSE or TEARDOWN
                if self.playEvent.isSet(): 
                    self.playTime = self.playTime + elapsed_time
                    elapsed_time = 0.0
                    print("PlayTime: " + str(real_playtime)) 
                    break
                
                # Upon receiving ACK for TEARDOWN request,
                # close the RTP socket
                if self.teardownAcked == 1:
                    self.playTime = self.playTime + elapsed_time
                    elapsed_time = 0.0
                    print("PlayTime: " + str(real_playtime)) 
                    self.rtpSocket.shutdown(socket.SHUT_RDWR)
                    self.rtpSocket.close()
                    break
                    
    def writeFrame(self, data):
        """Write the received frame to a temp image file. Return the image file."""
        cachename = CACHE_FILE_NAME + str(self.sessionId) + CACHE_FILE_EXT
        file = open(cachename, "wb")
        file.write(data)
        file.close()
        
        return cachename
    
    def updateMovie(self, imageFile):
        """Update the image file as video frame in the GUI."""
        photo = ImageTk.PhotoImage(Image.open(imageFile))
        self.label.configure(image = photo, height=288) 
        self.label.image = photo
        
    def connectToServer(self):
        """Connect to the Server. Start a new RTSP/TCP session."""
        self.rtspSocket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        try:
            self.rtspSocket.connect((self.serverAddr, self.serverPort))
        except:
            tkinter.messagebox.showwarning('Connection Failed', 'Connection to \'%s\' failed.' %self.serverAddr)
    
    def sendRtspRequest(self, requestCode):
        """Send RTSP request to the server."""
        #-------------
        # TO COMPLETE
        #-------------
 
        # Setup request
        if requestCode == self.SETUP and self.state == self.INIT:
            threading.Thread(target=self.recvRtspReply).start()
            print('setup clicked')
            # Update RTSP sequence number.
            # ...
            self.rtspSeq = self.rtspSeq + 1
            # Write the RTSP request to be sent.
            # request = ..
            request = "%s %s" % ('SETUP',self.fileName)
            request+="\nCSeq: %d" % self.rtspSeq
            request+="\nTransport: %s; client_port= %d" % ("RTP/UDP",self.rtpPort)

            # Keep track of the sent request.
            # self.requestSent = ...
            self.requestSent = self.SETUP
        
        # Play request
        elif requestCode == self.PLAY and self.state == self.READY:
            print('play clicked')		
            # Update RTSP sequence number.
            # ...
            self.rtspSeq = self.rtspSeq + 1
            # Write the RTSP request to be sent.
            # request = ...
            request = "%s %s" % ('PLAY',self.fileName)
            request+="\nCSeq: %d" % self.rtspSeq
            request+="\nSession: %d" % self.sessionId
            # Keep track of the sent request.
            # self.requestSent = ...
            self.requestSent = self.PLAY
        # Pause request
        
        elif requestCode == self.PAUSE and self.state == self.PLAYING:
            print('pause clicked')
            # Update RTSP sequence number.
            # ...
            self.rtspSeq = self.rtspSeq + 1
 
            # Write the RTSP request to be sent.
            # request = ...
            request = "%s %s" % ('PAUSE',self.fileName)
            request+="\nCSeq: %d" % self.rtspSeq
            # Keep track of the sent request.
            # self.requestSent = ...
            self.requestSent = self.PAUSE
 
        # Teardown request
        elif requestCode == self.TEARDOWN and not self.state == self.INIT:
            print('teardown clicked')
            # Update RTSP sequence number.
            # ...
            self.rtspSeq = self.rtspSeq + 1
 
            # Write the RTSP request to be sent.
            # request = ...
            request = "%s %s" % ('TEAR DOWN',self.fileName)
            request+="\nCSeq: %d" % self.rtspSeq
            # Keep track of the sent request.
            # self.requestSent = ...
            self.requestSent = self.TEARDOWN
        else:
            print('else statement')
            return
        
        # Send the RTSP request using rtspSocket.
        # ...
        request_as_bytes = str.encode(request)
        self.rtspSocket.send(request_as_bytes)
        print('\nData sent:\n' + request)
    
    def recvRtspReply(self):
        """Receive RTSP reply from the server."""
        print('recieved rtsp reply')
        while True:
            reply = self.rtspSocket.recv(1024)
            if reply: 
                self.parseRtspReply(reply)
            
            # Close the RTSP socket upon requesting Teardown
            if self.requestSent == self.TEARDOWN:
                self.rtspSocket.shutdown(socket.SHUT_RDWR)
                self.rtspSocket.close()
                break
    
    def parseRtspReply(self, data):
        print('reply being parsed')
        """Parse the RTSP reply from the server."""
        decodedData = data.decode() #^^^^^^
        lines = decodedData.split('\n')
        seqNum = int(lines[1].split(' ')[1])
        
        # Process only if the server reply's sequence number is the same as the request's
        if seqNum == self.rtspSeq:
            session = int(lines[2].split(' ')[1])
            # New RTSP session ID
            if self.sessionId == 0:
                self.sessionId = session
            
            # Process only if the session ID is the same
            if self.sessionId == session:
                if int(lines[0].split(' ')[1]) == 200: 
                    print('session id the same, changing RTSP state')
                    if self.requestSent == self.SETUP:
                        #-------------
                        # TO COMPLETE
                        #-------------
                        # Update RTSP state.
                        # self.state = ...
                        print('ready to play')
                        self.state = self.READY
                        # Open RTP port.
                        self.openRtpPort()
                    elif self.requestSent == self.PLAY:
                        print('currently playing')
                        # self.state = ...
                        self.state = self.PLAYING
                    elif self.requestSent == self.PAUSE:
                        print('paused, set state to ready')
                        # self.state = ...
                        self.state = self.READY
                        # The play thread exits. A new thread is created on resume.
                        self.playEvent.set()
                    elif self.requestSent == self.TEARDOWN:
                        # self.state = ...
                        self.state = self.INIT
                        # Flag the teardownAcked to close the socket.
                        self.teardownAcked = 1 
    
    def openRtpPort(self):
        """Open RTP socket binded to a specified port."""
        #-------------
        # TO COMPLETE
        #-------------
        # Create a new datagram socket to receive RTP packets from the server
        # self.rtpSocket = ...
        self.rtpSocket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
 
        # Set the timeout value of the socket to 0.5sec
        # ...
        self.rtpSocket.settimeout(0.5)
        
        try:
            # Bind the socket to the address using the RTP port given by the client user
            # ...
            self.state=self.READY
            self.rtpSocket.bind(('',self.rtpPort))
        except:
            tkinter.messagebox.showwarning('Unable to Bind', 'Unable to bind PORT=%d' %self.rtpPort)
 
    def handler(self):
        """Handler on explicitly closing the GUI window."""
        self.pauseMovie()
        if tkinter.messagebox.askokcancel("Quit?", "Are you sure you want to quit?"):
            self.exitClient()
        else: # When the user presses cancel, resume playing.
            self.playMovie()