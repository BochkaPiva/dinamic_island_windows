# SPDX-License-Identifier: GPL-3.0-only
"""Optical regression: displace only backdrop edges; preserve content and DPR."""
import unittest
import numpy as np
from PySide6.QtGui import QImage,QColor
from island.optics import lens_map,refract,light_field

class GlassOpticsTests(unittest.TestCase):
    def test_edges_displace_and_the_reading_center_is_unchanged(self):
        for scale in (1.,1.5,2.):
            w,h=round(320*scale),round(100*scale)
            sx,sy=lens_map(w,h,scale)
            y,x=np.mgrid[:h,:w]
            band=round(16*scale)
            self.assertTrue(np.array_equal(sx[band:-band,band:-band],x[band:-band,band:-band]))
            self.assertTrue(np.array_equal(sy[band:-band,band:-band],y[band:-band,band:-band]))
            self.assertGreater(np.count_nonzero((sx!=x)|(sy!=y)),0)
            self.assertLessEqual(np.max(np.hypot(sx-x,sy-y)),5*scale)
            self.assertTrue(np.all((sx>=0)&(sx<w)&(sy>=0)&(sy<h)))

    def test_pixel_sampling_alpha_and_device_ratio_survive_source_lifetime(self):
        source=QImage(120,80,QImage.Format.Format_RGBA8888);source.setDevicePixelRatio(1.5)
        for y in range(80):
            for x in range(120):source.setPixelColor(x,y,QColor(x*2,y*3,100,(x+y)%256))
        mapping=lens_map(120,80,1.5)
        result=refract(source,mapping)
        sx,sy=mapping
        for x,y in ((10,4),(60,40),(114,70)):
            self.assertEqual(result.pixelColor(x,y),source.pixelColor(int(sx[y,x]),int(sy[y,x])))
        source.fill(QColor('red'))
        self.assertNotEqual(result.pixelColor(60,40),QColor('red'))
        self.assertEqual(result.devicePixelRatio(),1.5)

    def test_invalid_shape_is_rejected_and_light_field_cache_is_bounded(self):
        with self.assertRaises(ValueError):lens_map(1,40)
        with self.assertRaises(ValueError):refract(QImage(10,10,QImage.Format.Format_RGBA8888),lens_map(20,20))
        for i in range(4):light_field(100+i,100,1.,False)
        self.assertLessEqual(light_field.cache_info().currsize,2)
