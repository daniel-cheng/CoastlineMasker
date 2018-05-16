# -*- coding: utf-8 -*-
"""
/***************************************************************************
 CoastlineMasker
                                 A QGIS plugin
 This plugin masks coastlines and returns a polygon mask of the selected window.
                              -------------------
        begin                : 2017-10-23
        git sha              : $Format:%H$
        copyright            : (C) 2017 by Daniel Cheng
        email                : dcheng334@gmail.com
 ***************************************************************************/

/***************************************************************************
 *                                                                         *
 *   This program is free software; you can redistribute it and/or modify  *
 *   it under the terms of the GNU General Public License as published by  *
 *   the Free Software Foundation; either version 2 of the License, or     *
 *   (at your option) any later version.                                   *
 *                                                                         *
 ***************************************************************************/
"""
from PyQt4.QtCore import QSettings, QTranslator, qVersion, QCoreApplication
from PyQt4.QtGui import QAction, QIcon, QFileDialog, QColor
from qgis.core import QgsRasterLayer, QgsVectorLayer, QgsCoordinateReferenceSystem, QgsRectangle, QgsVector, QgsMapLayer, QgsProject, QgsMapLayerRegistry
import qgis
# Initialize Qt resources from file resources.py
import resources
# Import the code for the dialog
from coastline_masker_dialog import CoastlineMaskerDialog
import os.path
import coastline_masker_core
import cv2

g_vectorLayer = []
class CoastlineMasker:
    """QGIS Plugin Implementation."""

    def __init__(self, iface):
        """Constructor.

        :param iface: An interface instance that will be passed to this class
            which provides the hook by which you can manipulate the QGIS
            application at run time.
        :type iface: QgsInterface
        """
        # Save reference to the QGIS interface
        self.iface = iface
        # initialize plugin directory
        self.plugin_dir = os.path.dirname(__file__)
        # initialize locale
        locale = QSettings().value('locale/userLocale')[0:2]
        locale_path = os.path.join(
            self.plugin_dir,
            'i18n',
            'CoastlineMasker_{}.qm'.format(locale))

        if os.path.exists(locale_path):
            self.translator = QTranslator()
            self.translator.load(locale_path)

            if qVersion() > '4.3.3':
                QCoreApplication.installTranslator(self.translator)


        # Declare instance attributes
        self.actions = []
        self.menu = self.tr(u'&Coastline Masker')
        # TODO: We are going to let the user set this up in a future iteration
        self.toolbar = self.iface.addToolBar(u'CoastlineMasker')
        self.toolbar.setObjectName(u'CoastlineMasker')

        # Create the dialog (after translation) and keep reference
        self.dlg = CoastlineMaskerDialog()

    # noinspection PyMethodMayBeStatic
    def tr(self, message):
        """Get the translation for a string using Qt translation API.

        We implement this ourselves since we do not inherit QObject.

        :param message: String for translation.
        :type message: str, QString

        :returns: Translated version of message.
        :rtype: QString
        """
        # noinspection PyTypeChecker,PyArgumentList,PyCallByClass
        return QCoreApplication.translate('CoastlineMasker', message)


    def add_action(
        self,
        icon_path,
        text,
        callback,
        enabled_flag=True,
        add_to_menu=True,
        add_to_toolbar=True,
        status_tip=None,
        whats_this=None,
        parent=None):
        """Add a toolbar icon to the toolbar.

        :param icon_path: Path to the icon for this action. Can be a resource
            path (e.g. ':/plugins/foo/bar.png') or a normal file system path.
        :type icon_path: str

        :param text: Text that should be shown in menu items for this action.
        :type text: str

        :param callback: Function to be called when the action is triggered.
        :type callback: function

        :param enabled_flag: A flag indicating if the action should be enabled
            by default. Defaults to True.
        :type enabled_flag: bool

        :param add_to_menu: Flag indicating whether the action should also
            be added to the menu. Defaults to True.
        :type add_to_menu: bool

        :param add_to_toolbar: Flag indicating whether the action should also
            be added to the toolbar. Defaults to True.
        :type add_to_toolbar: bool

        :param status_tip: Optional text to show in a popup when mouse pointer
            hovers over the action.
        :type status_tip: str

        :param parent: Parent widget for the new action. Defaults None.
        :type parent: QWidget

        :param whats_this: Optional text to show in the status bar when the
            mouse pointer hovers over the action.

        :returns: The action that was created. Note that the action is also
            added to self.actions list.
        :rtype: QAction
        """

        icon = QIcon(icon_path)
        action = QAction(icon, text, parent)
        action.triggered.connect(callback)
        action.setEnabled(enabled_flag)

        if status_tip is not None:
            action.setStatusTip(status_tip)

        if whats_this is not None:
            action.setWhatsThis(whats_this)

        if add_to_toolbar:
            self.toolbar.addAction(action)

        if add_to_menu:
            self.iface.addPluginToMenu(
                self.menu,
                action)

        self.actions.append(action)

        return action

    def initGui(self):
        """Create the menu entries and toolbar icons inside the QGIS GUI."""

        icon_path = ':/plugins/CoastlineMasker/icon.png'
        self.add_action(
            icon_path,
            text=self.tr(u'Coastline Masker'),
            callback=self.run,
            parent=self.iface.mainWindow())


    def unload(self):
        """Removes the plugin menu item and icon from QGIS GUI."""
        for action in self.actions:
            self.iface.removePluginMenu(
                self.tr(u'&Coastline Masker'),
                action)
            self.iface.removeToolBarIcon(action)
        # remove the toolbar
        del self.toolbar


    def run(self):
        """Run method that performs all the real work"""
        layers = self.iface.legendInterface().layers()
        raster_layer_list = []
        domain_layer_list = []
        for layer in layers:
            if layer.type() == QgsMapLayer.VectorLayer:
                domain_layer_list.append(layer.name())
            elif layer.type() == QgsMapLayer.RasterLayer:
                raster_layer_list.append(layer.name())

        
        raster_prefix_list = ['B5', 'BQA']
        
        toc = self.iface.legendInterface()
        root = QgsProject.instance().layerTreeRoot()
        groups = toc.groups()

        self.dlg.comboBox_rasterLayer.clear()
        self.dlg.comboBox_rasterPrefix.clear()
        self.dlg.comboBox_rasterGroup.clear()
        self.dlg.comboBox_domainLayer.clear()
        self.dlg.comboBox_rasterLayer.addItems(raster_layer_list)
        self.dlg.comboBox_rasterPrefix.addItems(raster_prefix_list)
        self.dlg.comboBox_rasterGroup.addItems(groups)
        self.dlg.comboBox_domainLayer.addItems(domain_layer_list)
        
        # show the dialog
        self.dlg.show()
        # Run the dialog event loop
        result = self.dlg.exec_()

        # See if OK was pressed
        if result:
            rasterLayerIndex = self.dlg.comboBox_rasterLayer.currentIndex()
            rasterPrefixIndex = self.dlg.comboBox_rasterPrefix.currentIndex()
            rasterGroupIndex = self.dlg.comboBox_rasterGroup.currentIndex()
            domainLayerIndex = self.dlg.comboBox_domainLayer.currentIndex()
            rasterLayerName = raster_layer_list[rasterLayerIndex]
            rasterPrefix = raster_prefix_list[rasterPrefixIndex]
            rasterGroupName = groups[rasterGroupIndex]
            domainLayerName = domain_layer_list[domainLayerIndex]
            
            rasterGroup = root.findGroup(rasterGroupName)
            rasterLayers = rasterGroup.findLayers()
            for layer in QgsMapLayerRegistry.instance().mapLayers().values():
                if layer.name() == domainLayerName:
                    domainLayer = layer
                    break
            
            for rasterLayer in rasterLayers:
                try:
                    if rasterLayer.name().endswith(rasterPrefix):
                        maskRasterLayer, maskVectorLayer = coastline_masker_core.maskFromLayers(rasterLayer.layer(), domainLayer, None, [5,15])
                        # step 1: add the layer to the registry, False indicates not to add to the layer tree
                        #QgsMapLayerRegistry.instance().addMapLayer(maskRasterLayer, False)
                        QgsMapLayerRegistry.instance().addMapLayer(maskVectorLayer, False)
                        # step 2: append layer to the root group node
                        #maskRasterLayerObject = rasterGroup.insertLayer(0, maskRasterLayer)
                        maskVectorLayerObject = rasterGroup.insertLayer(0, maskVectorLayer)
                        # step 3: Add transparency slider to layers
                        #maskRasterLayer.setCustomProperty("embeddedWidgets/count", 1)
                        #maskRasterLayer.setCustomProperty("embeddedWidgets/0/id", "transparency")      
                        #qgis.utils.iface.legendInterface().refreshLayerSymbology(maskRasterLayer)
                        maskVectorLayer.setCustomProperty("embeddedWidgets/count", 1)
                        maskVectorLayer.setCustomProperty("embeddedWidgets/0/id", "transparency")      
                        # Alter fill style for vector layers
                        symbols = maskVectorLayer.rendererV2().symbols()
                        symbol = symbols[0]
                        symbol.setColor(QColor.fromRgb(50,50,250,25))
                        # Redraw canvas and save variable to global context
                        qgis.utils.iface.legendInterface().refreshLayerSymbology(maskVectorLayer)
                        g_vectorLayer = maskVectorLayer
                except cv2.error as e:
                    print "OpenCV ERROR", e
                except Exception as e:
                    print e
                    
