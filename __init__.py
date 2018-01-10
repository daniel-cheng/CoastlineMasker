# -*- coding: utf-8 -*-
"""
/***************************************************************************
 CoastlineMasker
                                 A QGIS plugin
 This plugin masks coastlines and returns a polygon mask of the selected window.
                             -------------------
        begin                : 2017-10-23
        copyright            : (C) 2017 by Daniel Cheng
        email                : dcheng334@gmail.com
        git sha              : $Format:%H$
 ***************************************************************************/

/***************************************************************************
 *                                                                         *
 *   This program is free software; you can redistribute it and/or modify  *
 *   it under the terms of the GNU General Public License as published by  *
 *   the Free Software Foundation; either version 2 of the License, or     *
 *   (at your option) any later version.                                   *
 *                                                                         *
 ***************************************************************************/
 This script initializes the plugin, making it known to QGIS.
"""


# noinspection PyPep8Naming
def classFactory(iface):  # pylint: disable=invalid-name
    """Load CoastlineMasker class from file CoastlineMasker.

    :param iface: A QGIS interface instance.
    :type iface: QgsInterface
    """
    #
    from .coastline_masker import CoastlineMasker
    return CoastlineMasker(iface)
