# -*- coding: utf-8 -*-
#  The code was origionally done by Mathieu Leocmach
#  It was part of the Colloids library (https://github.com/MathieuLeocmach/colloids)
#  It is modified by Yushi Yang (yushi.yang@bristol.ac.uk) to be more compatable
#  with different python version and confocal machines
#  Since its' original version use GPL License, it's restricted GPL as well

# ============== origional information ====================
#
#    Copyright 2009 Mathieu Leocmach
#
#    This file is part of Colloids.
#
#    Colloids is free software: you can redistribute it and/or modify
#    it under the terms of the GNU General Public License as published by
#    the Free Software Foundation, either version 3 of the License, or
#    (at your option) any later version.
#
#    Colloids is distributed in the hope that it will be useful,
#    but WITHOUT ANY WARRANTY; without even the implied warranty of
#    MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
#    GNU General Public License for more details.
#
#    You should have received a copy of the GNU General Public License
#    along with Colloids.  If not, see <http://www.gnu.org/licenses/>.
#

import struct, io, re, sys
import xml
from xml.dom.minidom import parse
import numpy as np
from numpy.fft import rfft2, irfft2
import numexpr
import warnings

dimName = {1: "X",
           2: "Y",
           3: "Z",
           4: "T",
           5: "Lambda",
           6: "Rotation",
           7: "XT Slices",
           8: "TSlices",
           10: "unknown"}

channelTag = ["Gray", "Red", "Green", "Blue"]


class Header:
    """
    The XML header of a Leica LIF files
    
    Attributes:: are all semi-private (should only be accessed from a method getXXX()) 
                 as values are not supposed to be changed (they correspond to the *fixed* experimental conditions)
                 _version, _name, _seriesHeaders, 
    """

    def __init__(self, xmlHeaderFileName, quick=True):
        if sys.version_info > (3, 0):
            with open(xmlHeaderFileName, encoding="latin-1") as f:
                self.parse(f, quick)
        else:
            with open(xmlHeaderFileName) as f:
                self.parse(f, quick)

    def parse(self, xmlHeaderFile, quick=True):
        """
        Parse the usefull part of the xml header,
        stripping time stamps and non ascii characters
        """

        # to strip the non ascii characters
        t = "".join(map(chr, list(range(256))))
        d = "".join(map(chr, list(range(128, 256))))
        if sys.version_info > (3, 0):
            trans = str.maketrans('', '', d)
            lightXML = io.StringIO()
        else:
            import StringIO
            trans = {ord(c): None for c in d}
            lightXML = StringIO.StringIO()

        if not quick:
            # store all time stamps in a big array
            timestamps = np.fromregex(
                xmlHeaderFile,
                r'<TimeStamp HighInteger="(\d+)" LowInteger="(\d+)"/>',
                float
            )
            xmlHeaderFile.seek(0)
            relTimestamps = np.fromregex(
                xmlHeaderFile,
                r'<RelTimeStamp Time="(\f+)" Frame="(\d+)"/>|<RelTimeStamp Frame="[0-9]*" Time="[0-9.]*"/>',
                float
            )
            xmlHeaderFile.seek(0)
            if sys.version_info > (3, 0):
                for line in xmlHeaderFile:
                    lightXML.write(line.translate(trans))
            else:
                for line in xmlHeaderFile:
                    try:
                        lightXML.write(line.translate(t, d))
                    except TypeError:
                        lightXML.write(line.translate(trans))

        else:
            # to strip the time stamps
            m = re.compile(
                r'''<TimeStamp HighInteger="[0-9]*" LowInteger="[0-9]*"/>|'''
                + r'''<RelTimeStamp Time="[0-9.]*" Frame="[0-9]*"/>|'''
                + r'''<RelTimeStamp Frame="[0-9]*" Time="[0-9.]*"/>'''
            )
            if sys.version_info > (3, 0):
                for line in xmlHeaderFile:
                    lightXML.write(''.join(m.split(line)).translate(trans))
            else:
                for line in xmlHeaderFile:
                    try:
                        lightXML.write(''.join(m.split(line)).translate(t, d))
                    except TypeError:
                        lightXML.write(''.join(m.split(line)).translate(trans))
        lightXML.seek(0)
        self.xmlHeader = parse(lightXML)

    def getVersion(self):
        """
        Method: Get the version of the Data Container Header
        Semi-private attribute `_version`
        """
        if not hasattr(self, '_version'):
            self._version = self.xmlHeader.documentElement.getAttribute("Version")
        return int(self._version)

    def getName(self):
        """
        Method: Get the name of current lif file (without extension .lif)
        Semi-private attribute `_name`
        """
        if not hasattr(self, '_name'):
            self._name = self.xmlHeader.documentElement. \
                getElementsByTagName('Element')[0].getAttribute("Name")
        return self._name

    def getSeriesHeaders(self):
        """
        Method: Get the Series Headers of all series contained in the .lif file
        Semi-private attribute `_seriesHeaders`
        """

        if not hasattr(self, '_seriesHeaders'):
            root = self.xmlHeader.documentElement
            headers = []
            counter = 0
            for element in root.getElementsByTagName('Element'):
                element_nodes = [node for node in element.childNodes if node.ELEMENT_NODE == 1]
                memory_nodes = [node for node in element_nodes if (node.localName == 'Memory')]
                if len(memory_nodes) > 0:
                    counter += 1
                    memory_nodes = memory_nodes[0]
                    size = memory_nodes.getAttribute('Size')
                    if size:
                        if int(size) > 0:
                            headers.append(SerieHeader(element))
            self._seriesHeaders = headers
        return self._seriesHeaders

    def chooseSerieIndex(self):
        """
        Method: Interactive selection of the desired serie.
        
        Print a list of all Series specifying: index, Name, Channel number and Tag, and stack dimensions X, Y, Z, T,...
        Promt for selecting a Serie number.
        
        """
        st = "Experiment: %s\n" % self.getName()
        for i, s in enumerate(self.getSeriesHeaders()):
            # s = Serie(serie)
            st += "(%i) %s: %i channels and %i dimensions\n" % (
                i, s.getName(), len(s.getChannels()), len(s.getDimensions())
            )
            for c in s.getChannels():
                st += " %s" % channelTag[int(c.getAttribute("ChannelTag"))]
            for d in s.getDimensions():
                st += " %s%i" % (
                    dimName[int(d.getAttribute("DimID"))],
                    int(d.getAttribute("NumberOfElements"))
                )
            st += "\n"
        print(st)
        if len(self.getSeriesHeaders()) < 2:
            r = 0
        else:
            while (True):
                try:
                    r = int(input("Choose a serie --> "))
                    if r < 0 or r > len(self.getSeriesHeaders()):
                        raise ValueError()
                    break
                except ValueError:
                    print("Oops!  That was no valid number.  Try again...")
        return r

    def chooseSerieHeader(self):
        """
        Method: Interactive selection of the desired serie header.
        
        Print a list of all Series specifying: index, Name, Channel number and Tag, and stack dimensions X, Y, Z, T,...
        Promt for selecting a Serie number.
        
        """

        return self.getSeriesHeaders()[self.chooseSerieIndex()]

    def __iter__(self):
        return iter(self.getSeriesHeaders())


class SerieHeader:
    """The part of the XML header of a Leica LIF files concerning a given serie"""

    def __init__(self, serieElement):
        self.root = serieElement

    def getName(self):
        """
        Method: Get the Name of the Serie
        Semi-private attribute `_name`
        """
        if not hasattr(self, '_name'):
            self._name = self.root.getAttribute("Name")
        return self._name

    def isPreview(self):
        if not hasattr(self, '_isPreview'):
            self._isPreview = 0
            for c in self.root.getElementsByTagName("Attachment"):
                if c.getAttribute("Name") == "PreviewMarker":
                    self._isPreview = bool(c.getAttribute("isPreviewImage"))
                    break
        return self._isPreview

    def getChannels(self):
        """
        Method: Extract the DOM elements describing the used channels.
        Semi-private attribute `_channels`
        
        Return: List of DOM elements
        
        Use: To recover information contained in `chosen_serie.getChannels()`, iterate over the elements and apply `.getAttribute('Keyword')` method
        
        Keywords: Refer to xml file for a list of relevant Keywords. Examples: DataType, ChannelTag, Resolution, NameOfMeasuredQuantity, Min, Max, Unit, 
                  LUTName, IsLUTInverted, BytesInc, BitInc
        """
        if not hasattr(self, '_channels'):
            self._channels = self.root.getElementsByTagName("ChannelDescription")
        return self._channels

    def getDimensions(self):
        """
        Method: Extract the DOM elements describing the used channels.
        Semi-private attribute `_dimensions`
                
        Return: List of DOM elements
        
        Use: To recover information contained in `chosen_serie.getDimensionss()`, iterate over the elements and apply `.getAttribute('Keyword') method
        
        Keywords: Refer to xml file for a list of relevant Keywords. Examples: DimID, NumberOfElements, Origin, Length, Unit, BitInc, BytesInc
        """
        if not hasattr(self, '_dimensions'):
            self._dimensions = self.root.getElementsByTagName(
                "DimensionDescription")
        return self._dimensions

    def hasZ(self):
        """
        Method: Check if current serie includes Z stacking
        
        Return: Boolean value
        """
        for d in self.getDimensions():
            if dimName[int(d.getAttribute("DimID"))] == "Z":
                return True
        return False

    def getMemorySize(self):
        """
        Method: Get the Memory size of the current Serie
        Semi-private attribute `_memorySize`
        
        Return: Memory size as int
        """
        if not hasattr(self, '_memorySize'):
            for m in self.root.getElementsByTagName("Memory"):
                # to ensure the Memory node is the child of root
                if m.parentNode is self.root:
                    self._memorySize = int(m.getAttribute("Size"))
        return self._memorySize

    def getResolution(self, channel):
        """
        Method: Get the BitDepth Resolution of a given Channel using .getChannels() method
        Semi-private attribute `_resolution`

        arg:: channel number (int)
        
        Return: Bit Depth resolution as int
        """
        if not hasattr(self, '_resolution'):
            self._resolution = int(
                self.getChannels()[channel].getAttribute("Resolution")
            )
        return self._resolution

    def getScannerSetting(self, identifier):
        """
        Method: Access to the value of one of the Experimental Condition elements under ScannerSettingRecord TagName
        Semi-private attribute `_"identifier"`
        
        arg:: identifier (string) as the name of the Attribute looked for.
        
              Refer to xml file for a list of relevant identifier: dblPinhole, dblSizeX, dblSizeY, dblVoxelX, dblVoxelY, dblZoom, 
              nAccumulation, nAverageFrame, nAverageLine, nChannels, nDelayTime_ms, nLineAccumulation, nRepeatActions, ...
        
        return: The value ('Variant') of the required Attribute ('identifier') as a *string* 
        """
        if not hasattr(self, '_' + identifier):
            for c in self.root.getElementsByTagName("ScannerSettingRecord"):
                if c.getAttribute("Identifier") == identifier:
                    setattr(self, '_' + identifier, c.getAttribute("Variant"))
                    break
        return getattr(self, '_' + identifier)

    def getNumberOfElements(self):
        """
        Method: Use .getDimensions() method to extact the data dimensions along all axis in order X, Y, Z, T, ...
        Semi-private attribute `_numberOfElements`
        
        Result: List of integers
        """
        if not hasattr(self, '_numberOfElements'):
            self._numberOfElements = [
                int(d.getAttribute("NumberOfElements")) \
                for d in self.getDimensions()
            ]
        return self._numberOfElements

    def getVoxelSize(self, dimension):
        """
        Method: Use getScannerSetting() to return the resolution
        
        arg:: dimension is an integer according to the dimName dictionnary {1: X, 2: Y, 3: Z}
        
        Return: Voxel size of specified axis (float)

        """
        return float(self.getScannerSetting("dblVoxel%s" % dimName[dimension]))

    def getZXratio(self):
        """
        Method: Calculate for the current Serie the ratio between Vertical (Z) and Horizontal (X) image resolutions. Looks for the information either in
                    - 'ScannerSettingRecord' (resolution)
                    - or in 'DimensionDescription' (total size / pixel number)
        
        Return: Z/X resolution ratio (float). Return 1.0 if the current Serie has no Z-stack.
               
        """
        setting_records = self.root.getElementsByTagName('ScannerSettingRecord')
        dimension_descriptions = self.root.getElementsByTagName('DimensionDescription')
        if self.hasZ():
            if setting_records:
                return float(self.getScannerSetting("dblVoxelZ")) / float(self.getScannerSetting("dblVoxelX"))
            elif dimension_descriptions:
                length_x = float(
                    [d.getAttribute('Length') for d in dimension_descriptions if d.getAttribute('DimID') == '1'][0])
                length_z = float(
                    [d.getAttribute('Length') for d in dimension_descriptions if d.getAttribute('DimID') == '3'][0])
                number_x = float(
                    [d.getAttribute('NumberOfElements') for d in dimension_descriptions if
                     d.getAttribute('DimID') == '1'][
                        0])
                number_z = float(
                    [d.getAttribute('NumberOfElements') for d in dimension_descriptions if
                     d.getAttribute('DimID') == '3'][
                        0])
                psx = length_x / number_x
                psz = length_z / number_z
                return psz / psx
        else:
            return 1.0

    def getTotalDuration(self):
        """
        Method: Get total duration of the experiment using the .getDimensions() method
        Semi-private attribute `_duration`
        
        Return: duration (float) in seconds
        """
        if not hasattr(self, '_duration'):
            self._duration = 0.0
            for d in self.getDimensions():
                if dimName[int(d.getAttribute("DimID"))] == "T":
                    self._duration = float(d.getAttribute("Length"))
        return self._duration

    def getTimeLapse(self):
        """
        Method: Get an estimate of the average time lapse between two frames in seconds

        Return: estimated Lag time in seconds (float)
        
        warning:: Note that this value is accessible directly via getScannerSetting('nDelayTime_ms')
           
        """
        if self.getNbFrames() == 1:
            return 0
        else:
            return self.getTotalDuration() / (self.getNbFrames() - 1)

    def getTimeStamps(self):
        """if the timestamps are not empty, convert them into a more lightweight numpy array"""
        if not hasattr(self, '__timeStamps'):
            tslist = self.root.getElementsByTagName("TimeStampList")[0]
            if tslist.hasAttribute("NumberOfTimeStamps") and int(tslist.getAttribute("NumberOfTimeStamps")) > 0:
                # SP8 way of storing time stamps in the text of the node as 16bits hexadecimal separated by spaces
                self.__timeStamps = np.array([
                    int(h, 16)
                    for h in tslist.firstChild.nodeValue.split()
                ])
            else:
                # SP5 way of storing time stamps as very verbose XML
                self.__timeStamps = np.asarray([
                    (int(c.getAttribute("HighInteger")) << 32) + int(c.getAttribute("LowInteger"))
                    for c in self.root.getElementsByTagName("TimeStamp")])
                # remove the data from XML
                for c in self.root.getElementsByTagName("TimeStamp"):
                    c.parentNode.removeChild(c).unlink()
        return self.__timeStamps

    def getRelativeTimeStamps(self):
        """if the timestamps are not empty, convert them into a more lightweight numpy array"""
        if not hasattr(self, '__relTimeStamps'):
            self.__relTimeStamps = np.asarray([
                float(c.getAttribute("Time"))
                for c in self.root.getElementsByTagName("RelTimeStamp")])
            # remove the data from XML
            for c in self.root.getElementsByTagName("RelTimeStamp"):
                c.parentNode.removeChild(c).unlink()
        return self.__relTimeStamps

    def getBytesInc(self, dimension):
        """
        Method: Get the ByteIncrement of a given dimension in the Serie.
        Semi-private attribute `_"dim"`, with "dim" a string = X, Y, Z, T
        
        arg:: dimension either as a string or as its key (integer) in dimName = {1: "X", 2: "Y", 3: "Z", 4: "T", ...}
        
        Return: BytesIncr as integer
        """
        # todo: consider channels
        if isinstance(dimension, int):
            dim = dimName[dimension]
        else:
            dim = dimension
        if not hasattr(self, '_' + dim):
            setattr(self, '_' + dim, 0)
            for d in self.getDimensions():
                if dimName[int(d.getAttribute("DimID"))] == dim:
                    setattr(self, '_' + dim, int(d.getAttribute("BytesInc")))
        return getattr(self, '_' + dim)

    def chooseChannel(self):
        """
        Method: Interactive selection of the channel for the current serie.
        
        Print the Serie name `chosen_serie.getName() and a list of all channels specifying: index, Color
        Promt for selecting a channel index.
        
        """
        st = "Serie: %s\n" % self.getName()
        for i, c in enumerate(self.getChannels()):
            st += "(%i) %s\n" % (i, channelTag[int(c.getAttribute("ChannelTag"))])
        print(st)
        if len(self.getChannels()) < 2:
            r = 0
        while (True):
            try:
                r = int(input("Choose a channel --> "))
                if r < 0 or r > len(self.getChannels()):
                    raise ValueError()
                break
            except ValueError:
                print("Oops!  That was no valid number.  Try again...")
        return r

    def getNbFrames(self):
        """
        Method: Get the number of frames in the Serie (acquisition at successive times)
        Semi-private attribute `_nbFrames`
        
        Return: number of frames (integer)
        """
        if not hasattr(self, '_nbFrames'):
            self._nbFrames = 1
            for d in self.getDimensions():
                if d.getAttribute("DimID") == "4":
                    self._nbFrames = int(d.getAttribute("NumberOfElements"))
        return self._nbFrames

    def getBoxShape(self):
        """
        Method: Get the Shape (spatial) of a frame 
        Semi-private attribute: _boxShape
        
        Return: a list integers [length axis 1, length axis 2, ... ] ordered according to axis number (X, Y, Z)
        
        """
        if not hasattr(self, '_boxShape'):
            dims = {
                int(d.getAttribute('DimID')): int(d.getAttribute("NumberOfElements"))
                for d in self.getDimensions()
            }
            # ensure dimensions are sorted (unlike dictionnaries...), keep only spatial dimensions
            self._boxShape = [s for d, s in sorted(dims.items()) if d < 4]
        return self._boxShape

    def getFrameShape(self):
        """
        Method: Get the Shape of the frame (nD image) in C order, that is Z,Y,X 
        
        Return: list of integers of axis length in Z, Y, X order (reverse as in .getBoxShape())
        """
        return self.getBoxShape()[::-1]

    def get2DShape(self):
        """
        Method: Get the Shape of an image using the two first spatial dimensions, in C order, e.g. Y,X
        
        Return: list of integers of axis length
        """
        return self.getBoxShape()[:2][::-1]

    def getNbPixelsPerFrame(self):
        """
        Method: Get the total number of pixels in a frame of shape .getBoxShape()
        Semi-private attribute: _nbPixelsPerFrame
        
        Return: total number of pixels (integer) 
        """
        if not hasattr(self, '_nbPixelsPerFrame'):
            self._nbPixelsPerFrame = np.prod(self.getBoxShape())
        return self._nbPixelsPerFrame

    def getNbPixelsPerSlice(self):
        """
        Method: Get the total number of pixels in a Slice of shape .get2DShape()
        Semi-private attribute: _nbPixelsPerSlice
        
        Return: total number of pixels (integer) 
        """
        if not hasattr(self, '_nbPixelsPerSlice'):
            self._nbPixelsPerSlice = np.prod(self.get2DShape())
        return self._nbPixelsPerSlice


def get_xml(lif_name):
    """
    Function: Extract the XML header from LIF file and save it. Generated .xml file can be opened in a Web Browser
    
    Use to examine the global architecture and the keywords associated with usefull information, to use with getXXX() methods
    """
    with open(lif_name, "rb") as f:
        memBlock, trash, testBlock = struct.unpack("iic", f.read(9))
        if memBlock != 112:
            raise Exception("This is not a valid LIF file")
        if testBlock != b'*':
            raise Exception("Invalid block at %l" % f.tell())
        memorysize, = struct.unpack("I", f.read(4))
        # read and parse the header
        xml = f.read(2 * memorysize).decode("utf-16")
        return xml


class Reader(Header):
    """
    Reads Leica LIF files
    
    Methods: getSeries(), chooseSeries(), __init__(), __iter__(), __readMemoryBlockHeader()
    
    Semi-Private Attribute:: _series
                 

    """

    def __init__(self, lifFile, quick=True):
        # open file and find it's size
        if isinstance(lifFile, io.IOBase):
            self.f = lifFile
        else:
            self.f = open(lifFile, "rb")
        self.f.seek(0, 2)
        filesize = self.f.tell()
        self.f.seek(0)

        # read the size of the memory block containing the XML header
        # takes position at the begining of the XML header
        xmlHeaderLength = self.__readMemoryBlockHeader()

        # xmlHeaderLength, = struct.unpack("L",self.f.read(4))

        # Read the XML header as raw buffer. It should avoid encoding problems
        # but who uses japanese characters anyway
        xmlHeaderString = self.f.read(xmlHeaderLength * 2).decode('latin-1')
        self.parse(io.StringIO(xmlHeaderString[::2]), quick)

        # Index the series offsets
        self.offsets = []
        while (self.f.tell() < filesize):
            memorysize = self.__readMemoryBlockHeader()
            while (self.f.read(1) != b"*"):
                pass
            # size of the memory description
            memDescrSize, = struct.unpack("I", self.f.read(4))
            memDescrSize *= 2
            # skip the description: we are at the begining of the content
            self.f.seek(memDescrSize, 1)
            # add image offset if memory size >0
            if memorysize > 0:
                self.offsets.append(self.f.tell())
                self.f.seek(memorysize, 1)
        if not quick:
            # convert immediately the time stamps in XML format to lighweight numpy array
            for s in self:
                s.getTimeStamps()
                s.getRelativeTimeStamps()

        # self.offsets = [long(m.getAttribute("Size")) for m in self.xmlHEader.getElementsByTagName("Memory")]

    def __readMemoryBlockHeader(self):
        memBlock, trash, testBlock = struct.unpack("iic", self.f.read(9))
        if memBlock != 112:
            raise Exception("This is not a valid LIF file")
        if testBlock != b'*':
            raise Exception("Invalid block at %d" % self.f.tell())
        if not hasattr(self, 'xmlHeader') or self.getVersion() < 2:
            memorysize, = struct.unpack("I", self.f.read(4))
        else:
            memorysize, = struct.unpack("Q", self.f.read(8))
        return memorysize

    def getSeries(self):
        """
        Method: Get the experimental Series from the raw .lif file
        Semi-Private Attribute: _series
        
        Return: a List of class Serie objects
        """
        if not hasattr(self, '_series'):
            self._series = [
                Serie(s.root, self.f, self.offsets[i]) for i, s in enumerate(self.getSeriesHeaders())
            ]
        return self._series

    def chooseSerie(self):
        """
        Method: use .chooseSerieIndex() inherited Header method to interactively choose a Serie using .getSeries()
        
        Return: the selected class Serie object
        """
        return self.getSeries()[self.chooseSerieIndex()]

    def __iter__(self):
        return iter(self.getSeries())


class Serie(SerieHeader):
    """
    One of the datasets (Serie) in a .lif file
    
    Methods: 
    """

    def __init__(self, serieElement, f, offset):
        self.f = f
        self.__offset = offset
        self.root = serieElement

    def getOffset(self, **dimensionsIncrements):
        """
        Method: Get the Frame Offset
        
        kwargs:: Time, Channel or data type. Default to `channel=0, T=0, dtype=np.uint8`
        """
        of = 0
        for d, b in dimensionsIncrements.items():
            of += self.getBytesInc(d) * b
        if of >= self.getMemorySize():
            raise IndexError("offset out of bound")
        return self.__offset + of

    def getChannelOffset(self, channel):
        """
        Method: Get the Channel Offset
        
        arg:: channel (int)
        """
        channels = self.getChannels()
        channel_node = channels[channel]
        of = int(channel_node.getAttribute('BytesInc'))
        return of

    def get2DSlice(self, **dimensionsIncrements):
        """
        Method: Use the two first dimensions as image dimension (XY, XZ, YZ). Axis are in C order (last index is X).
        
        Return: Image as numpy array with the axis in ZY, ZX, or YX order
        
        warning:: See dtype argument; might not support 16bits encoding
        """
        for d in self.getDimensions()[:2]:
            if dimName[int(d.getAttribute("DimID"))] in dimensionsIncrements:
                raise Exception('You can\'t set %s in serie %s' % (
                    dimName[int(d.getAttribute("DimID"))],
                    self.getName())
                                )

        self.f.seek(self.getOffset(**dimensionsIncrements))
        shape = self.get2DShape()
        return np.fromfile(
            self.f,
            dtype=np.ubyte,
            count=self.getNbPixelsPerSlice()
        ).reshape(shape)

    def get2DString(self, **dimensionsIncrements):
        """
        Use the two first dimensions as image dimension
        """
        for d in self.getDimensions()[:2]:
            if dimName[int(d.getAttribute("DimID"))] in dimensionsIncrements:
                raise Exception('You can\'t set %s in serie %s' % (
                    dimName[int(d.getAttribute("DimID"))],
                    self.getName()))

        self.f.seek(self.getOffset(**dimensionsIncrements))
        return self.f.read(self.getNbPixelsPerSlice())

    def get2DImage(self, **dimensionsIncrements):
        """Use the two first dimensions as image dimension"""
        try:
            import Image
        except:
            try:
                if sys.version[0] == '2':
                    import PIL as Image
                elif sys.version[0] == '3':
                    from PIL import Image
                else:
                    print('Wrong Python Version')
                    return None
            except:
                print("Impossible to find image library")
                return None
        size = self.getNumberOfElements()[:2]
        return Image.fromstring(
            "L",
            tuple(size)
            , self.get2DString(**dimensionsIncrements)
        )

    def getFrame(self, channel=0, T=0, dtype=np.uint8):
        """
        Return a numpy array (C order, thus last index is X):
         2D if XYT or XZT serie,
         3D if XYZ, XYZT or XZYT
         (ok if no T dependence)
        Leica use uint8 by default, but after deconvolution the datatype is np.uint16
        """
        zcyx = []
        channels = self.getChannels()
        for z in range(self.getBoxShape()[-1]):
            cyx = []
            for i in range(len(channels)):
                self.f.seek(self.getOffset(**dict({'T': T, 'Z': z})) + self.getChannelOffset(i))
                yx = np.fromfile(self.f, dtype=dtype, count=int(self.getNbPixelsPerSlice()))
                yx = yx.reshape(self.get2DShape())
                cyx.append(yx)
            zcyx.append(cyx)
        zcyx = np.array(zcyx)
        xzcy = np.moveaxis(zcyx, -1, 0)
        xyzc = np.moveaxis(xzcy, -1, 1)
        return xyzc[:, :, :, channel]

    def getMetadata(self):
        """
        voxel size unit: µm
        """
        nbx, nby, nbz = self.getBoxShape()
        setting_records = self.root.getElementsByTagName('ScannerSettingRecord')
        dimension_descriptions = self.root.getElementsByTagName('DimensionDescription')
        if setting_records:
            # ScannerSettingRecord only available for some lif files!
            psx = self.getVoxelSize(1)  # m ---> µm
            psy = self.getVoxelSize(2)  # m ---> µm
            psz = self.getVoxelSize(3)  # m ---> µm
            unit_x = [s.getAttribute('Unit') for s in setting_records if s.getAttribute('Identifier') == 'dblVoxelX'][0]
            unit_y = [s.getAttribute('Unit') for s in setting_records if s.getAttribute('Identifier') == 'dblVoxelY'][0]
            unit_z = [s.getAttribute('Unit') for s in setting_records if s.getAttribute('Identifier') == 'dblVoxelZ'][0]
            units = [unit_x, unit_y, unit_z]
        elif dimension_descriptions:
            # Use DimensionDescription to get voxel information
            length_x = float(
                [d.getAttribute('Length') for d in dimension_descriptions if d.getAttribute('DimID') == '1'][0])
            length_y = float(
                [d.getAttribute('Length') for d in dimension_descriptions if d.getAttribute('DimID') == '2'][0])
            length_z = float(
                [d.getAttribute('Length') for d in dimension_descriptions if d.getAttribute('DimID') == '3'][0])
            number_x = float(
                [d.getAttribute('NumberOfElements') for d in dimension_descriptions if d.getAttribute('DimID') == '1'][
                    0])
            number_y = float(
                [d.getAttribute('NumberOfElements') for d in dimension_descriptions if d.getAttribute('DimID') == '2'][
                    0])
            number_z = float(
                [d.getAttribute('NumberOfElements') for d in dimension_descriptions if d.getAttribute('DimID') == '3'][
                    0])
            psx = length_x / number_x
            psy = length_y / number_y
            psz = length_z / number_z
            units = [s.getAttribute('Unit') for s in dimension_descriptions]
        else:
            raise RuntimeError("Can't find voxel information in the lif file!")

        if len(set(units)) == 1 and 'm' in units:
            factor = 1e6
            unit = 'um'
        else:
            warnings.warn('unit is not meter, check the unit of voxel size')
            factor = 1
            unit = ", ".join(units)

        psx = psx * factor  # m ---> µm
        psy = psy * factor  # m ---> µm
        psz = psz * factor  # m ---> µm

        return {
            'voxel_size_x': psx,
            'voxel_size_y': psy,
            'voxel_size_z': psz,
            'voxel_size_unit': unit,
            'voxel_number_x': nbx,
            'voxel_number_y': nby,
            'voxel_number_z': nbz,
            'channel_number': len(self.getChannels()),
            'frame_number': self.getNbFrames(),
        }

    def saveXML(self, name=None):
        if not name:
            name = '{}.xml'.format(self.getName())
        with open(name, 'w') as f:
            f.write(self.root.toprettyxml())

    def getVTK(self, fname, T=0):
        """
        Export the frame at time T to a vtk file
        One can render the vtk file using software like Paraview
        """
        if '.vtk' not in fname:
            fname += '.vtk'
        with open(fname, 'wb') as f:
            header = '# vtk DataFile Version 3.0\n%s\n' % self.getName +\
                'BINARY\nDATASET STRUCTURED_POINTS\n' +\
                ('DIMENSIONS %d %d %d\n' % tuple(self.getBoxShape())) +\
                'ORIGIN 0 0 0\n' +\
                ('SPACING 1 1 %g\n' % self.getZXratio()) +\
                ('POINT_DATA %d\n' % self.getNbPixelsPerFrame()) +\
                'SCALARS Intensity unsigned_char\nLOOKUP_TABLE default\n'
            f.write(str.encode(header))
            self.f.seek(self.getOffset(**dict({'T': T})))
            f.write(self.f.read(self.getNbPixelsPerFrame()))

    def enumByFrame(self):
        """yield time steps one after the other as a couple (time,numpy array). It is not safe to combine this syntax with getFrame or get2DSlice."""
        yield 0, self.getFrame()
        for t in range(1, self.getNbFrames()):
            yield t, np.fromfile(
                self.f,
                dtype=np.ubyte,
                count=self.getNbPixelsPerFrame()
            ).reshape(self.getFrameShape())

    def enumBySlice(self):
        """yield 2D slices one after the other as a 3-tuple (time,z,numpy array). It is not safe to combine this syntax with getFrame or get2DSlice."""
        self.f.seek(self.getOffset())
        for t in range(self.getNbFrames()):
            for z in range(self.getNbPixelsPerFrame() / self.getNbPixelsPerSlice()):
                yield t, z, np.fromfile(
                    self.f,
                    dtype=np.ubyte,
                    count=self.getNbPixelsPerSlice()
                ).reshape(self.get2DShape())


def getNeighbourhood(point, image, radius=10):
    box = np.floor([np.maximum(0, point - radius), np.minimum(image.shape, point + radius + 1)])
    ngb = image[box[0, 0]:box[1, 0], box[0, 1]:box[1, 1], box[0, 2]:box[1, 2]]
    center = point - box[0]
    return ngb, center


def getRadius(ngb, center, zratio=1, rmin=3, rmax=10, precision=0.1):
    sqdist = [(np.arange(ngb.shape[d]) - center[d]) ** 2 for d in range(ngb.ndim)]
    sqdist[-1] *= zratio ** 2
    dist = np.empty_like(ngb)
    for i, x in enumerate(sqdist[0]):
        for j, y in enumerate(sqdist[1]):
            for k, z in enumerate(sqdist[2]):
                dist[i, j, k] = x + y + z
    val = np.zeros(rmax / precision)
    nbs = np.zeros(rmax / precision)
    for l, (px, d) in enumerate(zip(ngb.ravel(), dist.ravel())):
        if d < rmax ** 2:
            i = int(np.sqrt(d) / precision)
            nbs[i] += 1
            val[i] += px
    intensity = np.cumsum(val) / np.cumsum(nbs)
    fi = np.fft.rfft(intensity)
    return rmin + precision * np.argmin(
        np.ediff1d(np.fft.irfft(
            fi * np.exp(-np.arange(len(fi)) / 13.5))
        )[rmin / precision:]
    )
