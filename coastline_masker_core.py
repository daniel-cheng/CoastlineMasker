import numpy as np
import cv2, processing, os
from osgeo import gdal
from gdalconst import *
from osgeo import osr
from pymasker import LandsatMasker
from pymasker import LandsatConfidence
from pyproj import Proj, transform

from PyQt4 import QtCore, QtGui
from PyQt4.QtCore import QFile, QFileInfo, QSettings
from PyQt4.QtGui import QAction, QIcon, QFileDialog
from qgis import core, gui, utils
from qgis.core import QgsRasterLayer, QgsCoordinateReferenceSystem, QgsRectangle, QgsVector, QgsVectorLayer
from qgis.gui import QgsMapCanvasLayer
from qgis.utils import iface

def geotiffBounds(geotiff):
    """Returns QgsRectangle representing bounds of geotiff in projection coordinates

    :geotiff: geotiff
    :bounds: QgsRectangle
    """
    geoTransform = geotiff.GetGeoTransform()
    
    xMin = geoTransform[0]
    yMax = geoTransform[3]
    xMax = xMin + geoTransform[1] * geotiff.RasterXSize
    yMin = yMax + geoTransform[5] * geotiff.RasterYSize

    return QgsRectangle(float(xMin), float(yMin), float(xMax), float(yMax))

def geotiffWorldToPixelCoords(geotiff, rectDomain, rasterCRS, domainCRS):
    """Transforms QgsRectangle coordinates into geotiff image pixel coordinates

    :geotiff: geotiff
    :rect: QgsRectangle
    """

    # Transform and scale rect by width/height to obtain normalized image coordiantes
    rectRef = geotiffBounds(geotiff)
    rectRefCenter = rectRef.center()

    rectRefWidth = rectRef.width()
    rectRefHeight = rectRef.height()

    domainX = [rectDomain.xMinimum(), rectDomain.xMaximum()]
    domainY = [rectDomain.yMinimum(), rectDomain.yMaximum()]
    inProj = Proj(init=domainCRS)
    outProj = Proj(init=rasterCRS)
    print domainX, domainY
    rasterCRSDomainX, rasterCRSDomainY = transform(inProj, outProj, domainX, domainY)
    print rasterCRSDomainX, rasterCRSDomainY

    xMin = (rasterCRSDomainX[0] - rectRef.xMinimum()) / rectRefWidth
    xMax = (rasterCRSDomainX[1] - rectRef.xMinimum()) / rectRefWidth
    yMin = (rasterCRSDomainY[0] - rectRef.yMinimum()) / rectRefHeight
    yMax = (rasterCRSDomainY[1] - rectRef.yMinimum()) / rectRefHeight

    # Scale by image dimensions to obtain pixel coordinates
    xMin = xMin * geotiff.RasterXSize
    xMax = xMax * geotiff.RasterXSize
    yMin = (1.0 - yMin) * geotiff.RasterYSize
    yMax = (1.0 - yMax) * geotiff.RasterYSize

    print rasterCRS, domainCRS

    #Return pixel coordinates
    rectOut = QgsRectangle(xMin, yMin, xMax, yMax)
    return rectOut

def arrayToRaster(array, geotiff, subset, destinationPath):
    """Array > Raster
    Save a raster from a C order array.

    :param array: ndarray
    """
    geoBounds = geotiffBounds(geotiff)
    geoTransform = geotiff.GetGeoTransform()

    # TODO: Fix X/Y coordinate mismatch and use ns/ew labels to reduce confusion. Also, general cleanup and refactoring.
    h, w = array.shape[:2]
    x_pixels = w  # number of pixels in x
    y_pixels = h  # number of pixels in y
    x_pixel_size = geoTransform[1]  # size of the pixel...        
    y_pixel_size = geoTransform[5]  # size of the pixel...        
    x_min = geoTransform[0] 
    y_max = geoTransform[3]  # x_min & y_max are like the "top left" corner.

    x_subset_percentage = 1.0 - (float(subset.yMinimum()) / float(geotiff.RasterYSize))
    y_subset_percentage = (float(subset.xMinimum()) / float(geotiff.RasterXSize))
    
    y_coordinate_range = geoBounds.width()
    x_coordinate_range = geoBounds.height()

    x_offset = x_subset_percentage * x_coordinate_range
    y_offset = y_subset_percentage * y_coordinate_range

    x_min = geoBounds.xMinimum() + int(y_offset)
    y_max = geoBounds.yMinimum() + int(x_offset)

    driver = gdal.GetDriverByName('GTiff')

    dataset = driver.Create(
        destinationPath,
        x_pixels,
        y_pixels,
        1,
        gdal.GDT_Float32, )

    dataset.SetGeoTransform((
        x_min,    # 0
        x_pixel_size,  # 1
        geoTransform[2],                      # 2
        y_max,    # 3
        geoTransform[4],                      # 4
        y_pixel_size))  #6
    
    dataset.SetProjection(geotiff.GetProjection())
    dataset.GetRasterBand(1).WriteArray(array)
    dataset.FlushCache()  # Write to disk.
    return dataset, dataset.GetRasterBand(1)  #If you need to return, remenber to return  also the dataset because the band don`t live without dataset.

def filterImage(geotiff,bounds,edgeMin=25,edgeMax=100,kernelSize=5):
    # Get first band and retrieve subset of image
    img = geotiff.GetRasterBand(1)
    img = img.ReadAsArray(0,0,geotiff.RasterXSize,geotiff.RasterYSize)
    img = img[int(round(bounds.yMinimum())):int(round(bounds.yMaximum())), int(round(bounds.xMinimum())):int(round(bounds.xMaximum()))]
    print int(round(bounds.yMinimum())), int(round(bounds.yMaximum())), int(round(bounds.xMinimum())), int(round(bounds.xMaximum()))
    print np.size(img)
   
    if np.size(img) == 0:
        raise cv2.error

    # Convert to 8 bit image for CV 
    img = (img/256).astype('uint8')

    # Filter images to remove noise
    # Median filter: http://docs.opencv.org/3.0-beta/modules/imgproc/doc/filtering.html#bilateralfilter
    img_mFilter = cv2.medianBlur(img,kernelSize)

    # Process edges
    img_edges = cv2.Canny(img,edgeMin,edgeMax,kernelSize)
    img_mFilter_edges = cv2.Canny(img_mFilter,edgeMin,edgeMax,kernelSize)

    return img_mFilter_edges

def processEdges(imageEdges):
    # Close edges to join them and dilate them before removing small components
    kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (3,3))
    closing = cv2.morphologyEx(imageEdges, cv2.MORPH_CLOSE, kernel)
    kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (3,3))
    dilated = cv2.dilate(closing,kernel,iterations = 1)
    largeComponents = removeSmallComponents(dilated)

    # Execute floodfill to generate land/sea mask
    flooded = largeComponents.copy()
    h, w = flooded.shape[:2]
    mask = np.zeros((h+2, w+2), np.uint8)
    connectivity = 8
    lo = 0
    hi = 50 
    flags = connectivity
    #if fixed_range:
    #    flags |= cv2.FLOODFILL_FIXED_RANGE
    cv2.floodFill(flooded, mask, (w - 1, 0), (255, 255, 255), (lo,)*3, (hi,)*3, flags)

    # Remove small components inside floodfill area
    floodedInverted = 255 - flooded
    floodedInverted = removeSmallComponents(floodedInverted)
    flooded = 255 - floodedInverted

    # Reverse initial morphological operators to retrieve original edge mask
    eroded = cv2.erode(flooded,kernel,iterations = 1)
    opening = cv2.morphologyEx(eroded, cv2.MORPH_OPEN, kernel)
    result = removeSmallComponents(opening)

    #contours experimental
    cv2.imwrite("output.png",opening)

    return result

def removeSmallComponents(image, min_size=1500):
    image = image.astype('uint8')
    #find all your connected components (white blobs in your image)
    nb_components, output, stats, centroids = cv2.connectedComponentsWithStats(image, connectivity=8)
    #connectedComponentswithStats yields every seperated component with information on each of them, such as size
    #the following part is just taking out the background which is also considered a component, but most of the time we don't want that.
    sizes = stats[1:, -1]; nb_components = nb_components - 1

    # minimum size of particles we want to keep (number of pixels)
    #here, it's a fixed value, but you can set it as you want, eg the mean of the sizes or whatever
    #min_size = 1500

    #your answer image
    largeComponents = np.zeros((output.shape))
    #for every component in the image, you keep it only if it's above min_size
    for i in range(0, nb_components):
        if sizes[i] >= min_size:
            largeComponents[output == i + 1] = 255
    return largeComponents.astype('uint8')

def vectorizeRaster(rasterPath, vectorName):
    """Description: Creates a vector layer from a raster using processing:polygonize.
        Make sure to save the shapefile, as it will be deleted otherwise! 
        Input:  string rasterPath - path to raster image to polygonize
                string vectorName - name to give new vector layer
        Output: QgsVectorLayer - object referencing the new vector layer
    """
    layer = processing.runalg('gdalogr:polygonize', rasterPath, 'DN', None)
    vectorPath = layer['OUTPUT']
    return QgsVectorLayer(vectorPath, vectorName, 'ogr')
    
def maskFromLayers(rasterLayer, domainLayer, outputLayer, thresholds):
    """Description: Processes a raster image into a vector polygon ocean/land mask.
        Make sure to save the shapefile, as it will be deleted otherwise! 
        Input:  QgsRasterLayer rasterLayer - layer that contains the raster image to process
                QgsVectorLayer domainLayer - layer that contains a polygon specifying the bounds of the raster image to process
                QgsVectorLayer outputLayer - layer to save vector layer in. Warning: not supported yet. 
        Output: QgsRasterLayer, QgsVectorLayer - objects referencing the new mask layers
    """

    # Get basic file name information on geotiff, raster image, masked raster subset image, and masked vector subset shp file
    fileSource = rasterLayer.source()
    fileInfo = QFileInfo(fileSource)
    filePath = fileInfo.absolutePath()
    fileName = fileInfo.baseName()
    fileQASource = filePath + os.path.sep + fileName[:fileName.rfind('_B')] + '_BQA.TIFF'
    maskName = fileName + '_masked'
    maskPath = filePath + os.path.sep + maskName + '.tif'
    polyMaskName = fileName + '_masked_polygon'
    polyMaskPath = filePath + os.path.sep + polyMaskName + '.shp'
    maskIceName = fileName + '_masked_ice'
    maskIcePath = filePath + os.path.sep + maskIceName + '.tif'
    maskCloudName = fileName + '_masked_cloud'
    maskCloudPath = filePath + os.path.sep + maskCloudName + '.tif'

    print fileSource

    # Load geotiff and get domain layer/bounding box of area to mask
    geotiff = gdal.Open(fileSource)
    feature = domainLayer.getFeatures().next()
    domain = feature.geometry().boundingBox()
    rasterCRS = rasterLayer.crs().authid()
    domainCRS = domainLayer.crs().authid()
    bounds = geotiffWorldToPixelCoords(geotiff, domain, rasterCRS, domainCRS)
    
    print domain.toString(), bounds.toString()
    
    # Generate QA masks
    #masker = LandsatMasker(fileQASource, collection=1)
    
    # algorithm has high confidence that this condition exists
    # (67-100 percent confidence)
    #conf = LandsatConfidence.high
    # Get mask indicating cloud pixels with high confidence
    #mask = masker.get_cloud_mask(conf)
    # save the result
    #masker.save_tif(mask, 'result.tif')

    # Execute masking algorithms
    filteredImage = filterImage(geotiff, bounds, thresholds[0], thresholds[1])
    mask = processEdges(filteredImage)

    # Save results to files and layers
    arrayToRaster(mask, geotiff, bounds, maskPath)
    #rasterLayer = iface.addRasterLayer(maskPath, maskName)
    #vectorLayer = vectorizeRaster(maskPath, polyMaskName)
    rasterLayer = QgsRasterLayer(maskPath, maskName)
    vectorLayer = vectorizeRaster(maskPath, polyMaskName)
    
    return rasterLayer, vectorLayer
