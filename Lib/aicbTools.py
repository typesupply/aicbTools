"""
A suite of simple tools for reading/writing
AICB data from/to the pasteboard.

Main Methods:
----------

- readAICBFromPasteboard
returns the AICB data or None from the appropriate pasteboard.

- drawAICBOutlines
draws the outlines in the AICB with a provided pen.

- AICBPen
writes AICB formatted data

Usage:
-----
data = readAICBFromPasteboard()
if data:
    didDraw = drawAICBOutlines(data, aPen)
    if not didDraw:
        print 'something was wrong with the AICB data'
"""

import re
from fontTools.pens.basePen import BasePen

###
### READER
###

boundingBox_RE = re.compile(
            "%%BoundingBox:\s"
            "([-\d\.\s]*)"
            )

layers_RE = re.compile(
            "^%AI5_BeginLayer$"
            "(.*)"
            "^%AI5_EndLayer--$",
            re.DOTALL+re.MULTILINE
            )

moveto_RE = re.compile(
        "^"
        "([-\d\.]+)"
        "\s"
        "([-\d\.]+)"
        "\s"
        "[m]"
        "$"
        )

lineto_RE = re.compile(
        "^"
        "([-\d\.]+)"
        "\s"
        "([-\d\.]+)"
        "\s"
        "[l|L]"
        "$"
        )
        
## a curve where the first bcp is the same as the previous on curve point
startCurveTo_RE = re.compile(
    "^"
    "([-\d\.]+)"
    "\s"
    "([-\d\.]+)"
    "\s"
    "([-\d\.]+)"
    "\s"
    "([-\d\.]+)"
    "\s"
    "[v|V]"
    "$"
    )

## a curve where the last bcp is the same as the next on curve point
endCurveTo_RE = re.compile(
    "^"
    "([-\d\.]+)"
    "\s"
    "([-\d\.]+)"
    "\s"
    "([-\d\.]+)"
    "\s"
    "([-\d\.]+)"
    "\s"
    "[y|Y]"
    "$"
    )

curveto_RE = re.compile(
        "^"
        "([-\d\.]+)"
        "\s"
        "([-\d\.]+)"
        "\s"
        "([-\d\.]*)"
        "\s"
        "([-\d\.]+)"
        "\s"
        "([-\d\.]+)"
        "\s"
        "([-\d\.]+)"
        "\s"
        "[c|C]"
        "$"
        )

# close path: h|H|f|s|N
# end path: n|S

def readAICBFromPasteboard():
    """
    get the AICB data from the NSPasteboard
    """
    from AppKit import NSPasteboard
    pb = NSPasteboard.generalPasteboard()
    types = [
        "CorePasteboardFlavorType 0x41494342",
        "com.adobe.encapsulated-postscript"
    ]
    data = None
    for typ in types:
        data = pb.dataForType_(typ)
        if data is not None:
            break
    if not data:
        return None
    data = data.bytes()
    try:
        if isinstance(data, memoryview):
            data = data.tobytes()
    except NameError:
        pass
    data = str(data)
    return data

def _getRectTransform(rect1, rect2, fixedScale=None):
    """
    return an affine transform matrix
    to fit rect2 inside of rect1
    """
    xMin1, yMin1, xMax1, yMax1 = rect1
    xMin2, yMin2, xMax2, yMax2 = rect2
    ##
    ## scaling
    ##
    if fixedScale is not None:
        scale = fixedScale
    else:
        # width
        widthScale = None
        if xMin1 is not None and xMax1 is not None and xMin2 is not None and xMax2 is not None:
            width1 = xMax1 - xMin1
            width2 = xMax2 - xMin2
            if width2 != 0:
                # scale down
                if width1 < width2:
                        widthScale = width1 / float(width2)
                # scale up
                elif width2 < width1:
                    widthScale = width1 / float(width2)
        # height
        heightScale = None
        if yMin1 is not None and yMax1 is not None and yMin2 is not None and yMax2 is not None:
            height1 = yMax1 - yMin1
            height2 = yMax2 - yMin2
            if height2 != 0:
                # scale down
                if height1 < height2:
                    heightScale = height1 / float(height2)
                # scale up
                elif height2 < height1:
                    heightScale = height1 / float(height2)
        # we don't have a destination rect
        if widthScale is None and heightScale is None:
            scale = 1.0
        # only fitting along the y
        elif widthScale is not None and heightScale is None:
            scale = widthScale
        # only fitting along the x
        elif widthScale is None and heightScale is not None:
            scale = heightScale
        # fitting both x and y
        else:
            scale = min(widthScale, heightScale)
    ##
    ## offset
    ##
    xOffset = 0
    if xMin1 is not None and xMax1 is not None and xMin2 is not None and xMax2 is not None:
        xMin2 = xMin2 * scale
        xMax2 = xMax2 * scale
        if xMin2 < xMin1:
            xOffset = xMin1 - xMin2
        elif xMax2 > xMax1:
            xOffset = xMax1 - xMax2
        # if the scaled rect is bigger than the 
        # dest rect, we center the scaled rect.
        width1 = xMax1 - xMin1
        width2 = xMax2 - xMin2
        if width2 > width1:
            xOffset = xOffset + ((width1 - width2) / 2.0)
    yOffset = 0
    if yMin1 is not None and yMax1 is not None and yMin2 is not None and yMax2 is not None:
        yMin2 = yMin2 * scale
        yMax2 = yMax2 * scale
        if yMin2 < yMin1:
            yOffset = yMin1 - yMin2
        elif yMax2 > yMax1:
            yOffset = yMax1 - yMax2
        # if the scaled rect is bigger than the 
        # dest rect, we center the scaled rect.
        height1 = yMax1 - yMin1
        height2 = yMax2 - yMin2
        if height2 > height1:
            yOffset = yOffset + ((height1 - height2) / 2.0)
    return (scale, 0, 0, scale, xOffset, yOffset)

def drawAICBOutlines(data, pen, fitInside=(None, None, None, None), fixedScale=None):
    """
    Draw outline data from an eps.
    Returns True if the data was drawn, False if not.

    data = the EPS data (string)
    pen = a drawing pen
    fitInside = the maximum size that the outline can be drawn into.
        the function will transform the eps outlines to fit within this box.
        if you don't want to transform the data, send it a box of (None, None, None, None).
        it is also possible to transform based on only horizontal OR vertical parameters.
        Simply send a box formatted like: (None, -250, None, 750) to base the transform
        on vertical dimensions or like: (-1000, None, 1000, None) to base the transform
        on horizontal dimensions.
    fixedScale = a set scale factor for transforming the outline. If the resulting scaled outline
        is larger than the fit rect, the outline will be centered on those parameters.
    """
    from fontTools.pens.transformPen import TransformPen
    from fontTools.misc.arrayTools import calcBounds
    data = '\n'.join(data.splitlines())
    ##
    ## get the point data
    # FL follows the EPSF3.0 spec, but AI seems
    # to be using a different spec. AI puts the outline data
    # in layers. we can get around this by iterating over all lines
    # in the data and drawing points as we find them.
    contours = []
    previousOnCurve = None
    for line in data.splitlines():
        movetoMatch = moveto_RE.match(line)
        if movetoMatch:
            contours.append([])
            x = float(movetoMatch.group(1))
            y = float(movetoMatch.group(2))
            contours[-1].append(('move', [(x, y)]))
            previousOnCurve = (x, y)
            continue
        linetoMatch = lineto_RE.match(line)
        if linetoMatch:
            x = float(linetoMatch.group(1))
            y = float(linetoMatch.group(2))
            contours[-1].append(('line', [(x, y)]))
            previousOnCurve = (x, y)
            continue
        startCurveToMatch = startCurveTo_RE.match(line)
        if startCurveToMatch:
            x1 = float(startCurveToMatch.group(1))
            y1 = float(startCurveToMatch.group(2))
            x2 = float(startCurveToMatch.group(3))
            y2 = float(startCurveToMatch.group(4))
            contours[-1].append(('curve', [previousOnCurve, (x1, y1), (x2, y2)]))
            previousOnCurve = (x2, y2)
            continue
        endCurveToMatch = endCurveTo_RE.match(line)
        if endCurveToMatch:
            x1 = float(endCurveToMatch.group(1))
            y1 = float(endCurveToMatch.group(2))
            x2 = float(endCurveToMatch.group(3))
            y2 = float(endCurveToMatch.group(4))
            contours[-1].append(('curve', [(x1, y1), (x2, y2), (x2, y2)]))
            previousOnCurve = (x2, y2)
            continue
        curvetoMatch = curveto_RE.match(line)
        if curvetoMatch:
            x1 = float(curvetoMatch.group(1))
            y1 = float(curvetoMatch.group(2))
            x2 = float(curvetoMatch.group(3))
            y2 = float(curvetoMatch.group(4))
            x3 = float(curvetoMatch.group(5))
            y3 = float(curvetoMatch.group(6))
            contours[-1].append(('curve', [(x1, y1), (x2, y2), (x3, y3)]))
            previousOnCurve = (x3, y3)
            continue
    # no outline data. give up.
    if not contours:
        return False
    ## get the bounding box
    boundingBox = boundingBox_RE.findall(data)
    if boundingBox:
        # rudely assume that there is only one EPS level bounding box
        # (the spec says that it should be that way)
        boundingBox = [
                int(i.split('.')[0])    # FL writes floats in the bounding box
                for i in boundingBox[0].split(' ')
                ]
    # the EPS does not have a bounding box
    # or the EPS has a stated box of (0, 0, 0, 0)
    # (which AI seems to do for open paths!)
    # so, we get the bounds from a points array
    if not boundingBox or boundingBox == [0, 0, 0, 0]:
        points = []
        for contour in contours:
            for tp, pts in contour:
                points.extend(pts)
        boundingBox = calcBounds(points)
    ##
    ## determine if the outlines need to be transformed
    ## and set up the transformation pen.
    transform = _getRectTransform(fitInside, boundingBox, fixedScale)
    transformPen = TransformPen(pen, transform)
    ##
    ## finally, draw the points
    for contour in contours:
        haveClosedPath = False
        if len(contour) > 1:
            # filter out overlapping points at the
            # start and the end of the contour
            start = contour[0]
            end = contour[-1]
            if end[0] == 'line':
                startPoints = start[1]
                endPoints = end[1]
                if start[0] == end[0]:
                    contour = contour[:-1]
                    haveClosedPath = True
        for tp, pts in contour:
            if tp == 'move':
                transformPen.moveTo(pts[0])
            elif tp == 'line':
                transformPen.lineTo(pts[0])
            elif tp == 'curve':
                pt1, pt2, pt3 = pts
                transformPen.curveTo(pt1, pt2, pt3)
        transformPen.closePath()
        # XXX
        #if haveClosedPath:
        #   transformPen.closePath()
        #else:
        #   transformPen.endPath()
    return True


###
### WRITER
###

def _timeStamp():
    import time
    monthList =[
        'January',
        'February',
        'March',
        'April',
        'May',
        'June',
        'July',
        'August',
        'September',
        'October',
        'November',
        'December'
        ]
    dayList = [
        'Sunday',
        'Monday',
        'Tuesday',
        'Wednesday',
        'Thursday',
        'Friday',
        'Saturday'
        ]
    year, month, date, hour, minute, second, weekday, yearday, dst = time.localtime()
    hour = str(hour).zfill(2)
    minute = str(minute).zfill(2)
    second = str(int(second)).zfill(2)
    return "%s %s %s:%s:%s %d" % (dayList[weekday], monthList[month-1], hour, minute, second, year)

_epsDict = """/AICBPen 24 dict def AICBPen begin
/Version 0 def
/bd {bind def} def
/n {newpath} bd
/c {curveto} bd
/C {curveto} bd
/L {lineto} bd
/l {lineto} bd
/m {moveto} bd
/f {closepath} bd
/S {} bd
/*u { } bd
/*U { fill} bd
/A {pop} bd
/O {pop} bd
/D {pop} bd
/g {setgray} bd
end"""

_epsSetup = """%%BeginSetup
AICBPen begin
n
%%EndSetup"""

_epsTrailer = """*U
%%PageTrailer
showpage
%%Trailer
end
%%EOF"""

class AICBPen(BasePen):

    def __init__(self, glyphSet, boundingBox, creator="AICBPen"):
        BasePen.__init__(self, glyphSet)
        boundingBox = ' '.join([str(i) for i in boundingBox])
        self._epsData = [
                "%!PS-Adobe-3.0",
                "%%%%Creator: %s" % creator,
                "%%%%Title: %s Data" % creator,
                "%%%%CreationDate: %s" % _timeStamp(),
                "%%%%BoundingBox: %s" % boundingBox,
                "%%EndComments",
                "%%BeginProlog",
                _epsDict,
                "%%EndProlog",
                _epsSetup,
                "0 A  *u 0 O 0 g",
                ]
        self._firstPoint = None 
        self._currentPoint = None

    def _moveTo(self, pt):
        # XXX this isn't right as it can be 1 or 0
        # indicates direction???
        self._epsData.append("0 D")
        s = "%s %s m" % (str(pt[0]), str(pt[1]))
        self._epsData.append(s)
        self._firstPoint = pt
        self._currentPoint = pt

    def _lineTo(self, pt):
        s = "%s %s l" % (str(pt[0]), str(pt[1]))
        self._epsData.append(s)
        self._currentPoint = pt

    def _curveToOne(self, pt1, pt2, pt3):
        s = "%s %s %s %s %s %s c" % (str(pt1[0]), str(pt1[1]), str(pt2[0]), str(pt2[1]), str(pt3[0]), str(pt3[1]))
        self._epsData.append(s)
        self._currentPoint = pt3

    def _closePath(self):
        if self._firstPoint != self._currentPoint:
            self.lineTo(self._firstPoint)
        self._epsData.append("f")

    def _endPath(self):
        self._epsData.append("f")

    def getData(self):
        return '\n'.join(self._epsData+[_epsTrailer])