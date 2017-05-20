import weakref
import ifigure.events as events
from scipy.signal import convolve2d, fftconvolve

from matplotlib.axes import Axes
from matplotlib.lines import Line2D
from matplotlib.text import Text
from mpl_toolkits.mplot3d.axes3d import Axes3D
import mpl_toolkits.mplot3d.proj3d as proj3d
import mpl_toolkits.mplot3d.art3d as art3d
import matplotlib.transforms as trans
from matplotlib.colors import ColorConverter
cc = ColorConverter()

from matplotlib.artist import allow_rasterization
import numpy as np
from matplotlib.collections import Collection, LineCollection, \
        PolyCollection, PatchCollection, PathCollection
from ifigure.matplotlib_mod.is_supported_renderer import isSupportedRenderer

### KERNEL for mask bluring
conv_kernel_size = 11
x = 1-np.abs(np.linspace(-1., 1., conv_kernel_size))
X, Y = np.meshgrid(x, x)
conv_kernel = np.sqrt(X**2, Y**2)
conv_kernel = conv_kernel/np.sum(conv_kernel)
###             
def convert_to_gl(obj, zs = 0, zdir = 'z'):
    from art3d_gl import polygon_2d_to_gl 
    from art3d_gl import line_3d_to_gl 
    from art3d_gl import poly_collection_3d_to_gl
    from art3d_gl import line_collection_3d_to_gl     
    from matplotlib.patches import Polygon
    from mpl_toolkits.mplot3d.art3d import Poly3DCollection, Line3D, \
                           poly_collection_2d_to_3d, Line3DCollection

    if isinstance(obj, Line3D):
       line3d_to_gl(obj)
    elif isinstance(obj, Polygon):
       polygon_2d_to_gl(obj, zs, zdir)
    elif isinstance(obj, Poly3DCollection):
       poly_collection_3d_to_gl(obj)
    elif isinstance(obj, Line3DCollection):
       line_collection_3d_to_gl(obj)        
    elif isinstance(obj, PolyCollection):
       poly_collection_2d_to_3d(obj, zs=zs, zdir=zdir)
       poly_collection_3d_to_gl(obj)

def get_glcanvas():
    from ifigure.matplotlib_mod.backend_wxagg_gl import FigureCanvasWxAggModGL
    return FigureCanvasWxAggModGL.glcanvas

def norm_vec(n):
    d = np.sum(n**2)
    if d == 0:
       return [0,0,0]
    else:
       return n/np.sqrt(d)

def arrow3d(base, r1, r2, ort, l, h, m = 13, pivot = 'tail'):
    x = np.array([1., 0., 0.])
    y = np.array([0., 1., 0.])
    th = np.linspace(0, np.pi*2, m).reshape(-1,1)
    ort = norm_vec(ort)
    if np.sum(ort * x) == 0:
       d1 = norm_vec(np.cross(ort, y))
    else:
       d1 = norm_vec(np.cross(ort, x))
    if pivot == 'tip':
       base = base - (l+h)*ort
    elif pivot == 'mid':
       base = base - (l+h)*ort/2.
    else:
       pass
    d2 = np.cross(ort, d1)
    p = base + l*r1* (d1*np.cos(th) + d2*np.sin(th))
    q = p + l*ort
    p2 = base + l*r2* (d1*np.cos(th) + d2*np.sin(th)) + l*ort
    p3 = base + (l+h)*ort 
    p3 = np.array([p3]*m).reshape(-1, 3)
    t1 = np.stack((p[:-1], q[:-1], p[1:]), axis=1)
    t2 = np.stack((p[1:], q[:-1], q[1:]), axis=1)
    t3 = np.stack((p2[:-1], p3[:-1], p2[1:]), axis=1)
    #t2 = np.dstack((p[1:], q[:-1], q[1:]))
    t1  = np.vstack((t1, t2, t3))
    return t1


from functools import wraps
def use_gl_switch(func):
    '''
    use_gl_switch allows to select types of 3D plot
    aritist, either mplot3d or openGL based artist.

    note that piScope does not keep track
    use_gl switch. Manipulating use_gl manually in 
    piScope makes your plot unreproducible.
    '''
    @wraps(func)
    def checker(self, *args, **kargs):
        if self._use_gl:
            m = func
            ret = m(self, *args, **kargs)            
        else:
            m = getattr(super(Axes3DMod, self), func.__name__)
            ret = m(*args, **kargs)
        return ret
    return checker

from matplotlib.image import FigureImage
class ArtGLHighlight(FigureImage):
    def remove(self):
        self.figure.artists.remove(self)

class Axes3DMod(Axes3D):
    pan_sensitivity = 5
    def __init__(self, *args, **kargs):
        self._nomargin_mode = False
        self._offset_trans_changed = False
        self._mouse_hit = False
        self._lighting = {'light'      : 0.,
                          'ambient'    : 1.0,
                          'specular'   : .0,
                          'light_direction'  : (1., 0, 1, 0),
                          'light_color'      : (1., 1., 1), 
                          'wireframe'      : 0,
                          'clip_limit1'    : [0., 0.,0. ],
                          'clip_limit2'    : [1., 1.,1. ],
                          'shadowmap' : False}        
        self._use_gl = kargs.pop('use_gl', True)
        self._use_frustum = kargs.pop('use_frustum', True)
        self._use_clip =    kargs.pop('use_clip', True)        
        super(Axes3DMod, self).__init__(*args, **kargs)
        self.axesPatch.set_alpha(0)
        self._gl_id_data = None
        self._gl_mask_artist = None
        self._3d_axes_icon = None
        self._show_3d_axes = True
        self._upvec = np.array([0,0,1])

    def gl_hit_test(self, x, y, id, radius = 3):
        #
        #  logic is
        #     if artist_id is found within raidus from (x, y)
        #     and
        #     if it is the closet artist in the area of checking
        #     then return True
        if self._gl_id_data is None: return False
        
        x0, y0, id_dict, im, im2 = self._gl_id_data
        x, x0,  y, y0 = int(x), int(x0),  int(y), int(y0)        
        d = np.rint((im[y-y0-radius:y-y0+radius, x-x0-radius:x-x0+radius]).flatten())
        dd = (im2[y-y0-radius:y-y0+radius, x-x0-radius:x-x0+radius]).flatten()
        if len(dd) == 0: return False
        dist = np.min(dd)
        for num, check in zip(d, dd):
            if num in id_dict:
                if id_dict[num] == id and check == dist:
                   return True

        return False

    def make_gl_hl_artist(self):
        if self._gl_id_data is None: return []
        self.del_gl_hl_artist()
            
        x0, y0, id_dict, im, im2 = self._gl_id_data
        a = ArtGLHighlight(self.figure, offsetx = x0,
                            offsety = y0, origin='lower')
        data = np.ones(im.shape)
        alpha = np.zeros(im.shape)        
        mask = np.dstack((data,data,data, alpha))
        a.set_array(mask)
        self.figure.artists.append(a)
        self._gl_mask_artist = a

        return [a]
    
    def del_gl_hl_artist(self):
        if self._gl_mask_artist is not None:
            self._gl_mask_artist.remove()
        self._gl_mask_artist = None
        
    def set_gl_hl_mask(self, id, cmask = 0.0, amask = 0.65):
        #
        #  logic is
        #     if artist_id is found within raidus from (x, y)
        #     and
        #     if it is the closet artist in the area of checking
        #     then return True

        
        if self._gl_id_data is None: return False
        if self._gl_mask_artist is None: return False

        # do not do this when hitest_map is updating..this is when
        # mouse dragging is going on
        if not get_glcanvas()._hittest_map_update: return
        x0, y0, id_dict, im, im2 = self._gl_id_data
              
        arr = self._gl_mask_artist.get_array()
        for k in id_dict.keys():
            if (id_dict[k] == id):
               m = im == k
               arr[:,:,0][m] = cmask
               #arr[:,:,1][m] = cmask
               #arr[:,:,2][m] = cmask
               arr[:,:,3][m] = amask               
               break
        # blur the mask,,,

    def blur_gl_hl_mask(self, cmask = 0.0, amask = 0.65):
        if self._gl_mask_artist is None: return
        arr = self._gl_mask_artist.get_array()
        #b = convolve2d(arr[:,:,3], conv_kernel, mode = 'same') + arr[:,:,3]
        b = fftconvolve(arr[:,:,3], conv_kernel, mode = 'same') + arr[:,:,3]
        #b = np.sqrt(b)
        b[b > amask] = amask
        a = arr[:,:,0]; a[b > 0.0] = cmask        
        arr = np.dstack((a,a,a,b))
        self._gl_mask_artist.set_array(arr)

    def set_nomargin_mode(self, mode):
        self._nomargin_mode = mode

    def get_nomargin_mode(self):
        return self._nomargin_mode
    
    def get_zaxis(self):
        return self.zaxis

    #
    #   prepend and append some work to visual
    #   effect for 3D rotation
    #
    def set_mouse_button(self, rotate_btn=1, zoom_btn=3, pan_btn=2):
        self._pan_btn = np.atleast_1d(pan_btn)
        self._rotate_btn = np.atleast_1d(rotate_btn)
        self._zoom_btn = np.atleast_1d(zoom_btn)

#    def mouse_init(self, rotate_btn=1, zoom_btn=3, pan_btn=2):
#        self.set_mouse_button(rotate_btn=rotate_btn, 
#                              zoom_btn=zoom_btn, 
#                              pan_btn=pan_btn)
#        self._pan_btn = np.atleast_1d(pan_btn)
#        self._rotate_btn = np.atleast_1d(rotate_btn)
#        self._zoom_btn = np.atleast_1d(zoom_btn)
#        Axes3D.mouse_init(self, rotate_btn=rotate_btn, zoom_btn=zoom_btn)

    def _button_press(self, evt):
        self._mouse_hit, extra = self.contains(evt)
        if not self._mouse_hit:return
        fig_axes = self.figobj
#        for obj in fig_axes.walk_tree():
#            obj.switch_scale('coarse')
        Axes3D._button_press(self, evt)

    def _on_move(self, evt):
        if not self._mouse_hit:return
        fig_axes = self.figobj
        fig_axes.set_bmp_update(False)
        #Axes3D._on_move(self, evt)    
        self._on_move_mod(evt)    
        get_glcanvas()._hittest_map_update = False
        events.SendPVDrawRequest(self.figobj, 
                                 w=None, wait_idle=False, 
                                 refresh_hl=False)
    def _on_move_done(self):
        get_glcanvas()._hittest_map_update = True

    def _on_move_mod(self, event):
        """
        added pan mode 
        """

        if not self.button_pressed:
            return

        if self.M is None:
            return

        x, y = event.xdata, event.ydata
        # In case the mouse is out of bounds.
        if x is None:
            return

        dx, dy = x - self.sx, y - self.sy
        w = self._pseudo_w
        h = self._pseudo_h
        self.sx, self.sy = x, y

        # Rotation
        if self.button_pressed in self._rotate_btn:
            # rotate viewing point
            # get the x and y pixel coords
            if dx == 0 and dy == 0:
                return
            relev, razim = np.pi * self.elev/180, np.pi * self.azim/180
            p1 = np.array((np.cos(razim) * np.cos(relev),
                           np.sin(razim) * np.cos(relev),
                           np.sin(relev)))
            rightvec = np.cross(self._upvec, p1)
            #dx = dx/np.sqrt(dx**2 + dy**2)/3.
            #dy = dy/np.sqrt(dx**2 + dy**2)/3.
            newp1 = p1 - (dx/w*rightvec + dy/h*self._upvec)*Axes3DMod.pan_sensitivity
            newp1 = newp1/np.sqrt(np.sum(newp1**2))
            self._upvec = self._upvec - newp1*np.sum(newp1*self._upvec)
            self._upvec = self._upvec/np.sqrt(np.sum(self._upvec**2))
            self.elev = np.arctan2(newp1[2], np.sqrt(newp1[0]**2+newp1[1]**2))*180/np.pi
            self.azim = np.arctan2(newp1[1], newp1[0])*180/np.pi
#            self.elev = art3d.norm_angle(self.elev - (dy/h)*180)
#            self.azim = art3d.norm_angle(self.azim - (dx/w)*180)
            self.get_proj()
            self.figure.canvas.draw_idle()

        elif self.button_pressed in self._pan_btn:
            dx = 1-((w - dx)/w)
            dy = 1-((h - dy)/h)
            relev, razim = np.pi * self.elev/180, np.pi * self.azim/180
            p1 = np.array((np.cos(razim) * np.cos(relev),
                           np.sin(razim) * np.cos(relev),
                           np.sin(relev)))
            rightvec = np.cross(self._upvec, p1)  # right on screen

            #p2 = np.array((np.sin(razim), -np.cos(razim), 0))
            #p3 = np.cross(p1, p2)
            #dx, dy, dz = p2*dx + p3*dy
            dx, dy, dz = -rightvec * dx - self._upvec* dy
            minx, maxx, miny, maxy, minz, maxz = self.get_w_lims()
            dx = (maxx-minx)*dx
            dy = (maxy-miny)*dy
            dz = (maxz-minz)*dz

            self.set_xlim3d(minx + dx, maxx + dx)
            self.set_ylim3d(miny + dy, maxy + dy)
            self.set_zlim3d(minz + dz, maxz + dz)

            self.get_proj()
            self.figure.canvas.draw_idle()

            # pan view
            # project xv,yv,zv -> xw,yw,zw
            # pan
#            pass

        # Zoom
        elif self.button_pressed in self._zoom_btn:
            # zoom view
            # hmmm..this needs some help from clipping....
            minx, maxx, miny, maxy, minz, maxz = self.get_w_lims()
            df = 1-((h - dy)/h)
            dx = (maxx-minx)*df
            dy = (maxy-miny)*df
            dz = (maxz-minz)*df
            self.set_xlim3d(minx - dx, maxx + dx)
            self.set_ylim3d(miny - dy, maxy + dy)
            self.set_zlim3d(minz - dz, maxz + dz)
            self.get_proj()
            self.figure.canvas.draw_idle()

    def _button_release(self, evt):
        if not self._mouse_hit:return
        Axes3D._button_release(self, evt)
        fig_axes = self.figobj
#        for obj in fig_axes.walk_tree():
#            obj.switch_scale('fine')
        fig_axes.set_bmp_update(False)
        events.SendPVDrawRequest(self.figobj, 
                                 w=None, wait_idle=False, 
                                 refresh_hl=False)
    @use_gl_switch
    def plot(self, *args, **kwargs):
        from art3d_gl import line_3d_to_gl
        if len(args) == 4:
            c = args[-1]
            args = args[:3]
        else: c = None
        fc = kwargs.pop('facecolor', None)
        gl_offset = kwargs.pop('gl_offset', (0,0,0))
        lines = Axes3D.plot(self, *args, **kwargs)
        for l in lines:
            line_3d_to_gl(l)
            l._facecolor = fc
            l._gl_offset = gl_offset
#            if c is not None:
#                l._gl_solid_edgecolor = None
#                l._c_data = c
#            else:
#                print l.get_color()
#                l._gl_solid_edgecolor = l.get_color()                
        return lines

    def fill(self, *args, **kwargs):
        from art3d_gl import polygon_2d_to_gl 
        zs = kwargs.pop('zs', 0)
        zdir = kwargs.pop('zdir', 'z')
        a = Axes3D.fill(self, *args, **kwargs)


        for obj in a: convert_to_gl(obj, zs, zdir)
        return a

    def fill_between(self, *args, **kwargs):
        from art3d_gl import polygon_2d_to_gl 
        zs = kwargs.pop('zs', 0)
        zdir = kwargs.pop('zdir', 'z')
        a = Axes3D.fill_between(self, *args, **kwargs)
        convert_to_gl(a, zs, zdir)
        a.convert_2dpath_to_3dpath(zs, zdir = zdir)                
        return a

    def fill_betweenx(self, *args, **kwargs):
        from art3d_gl import polygon_2d_to_gl 
        zs = kwargs.pop('zs', 0)
        zdir = kwargs.pop('zdir', 'z')
        a = Axes3D.fill_betweenx(self, *args, **kwargs)
        convert_to_gl(a, zs, zdir)
        a.convert_2dpath_to_3dpath(zs, zdir = zdir)        
        return a
    
    def cz_plot(self, x, y, z, c, **kywds):
        from ifigure.matplotlib_mod.art3d_gl import Line3DCollectionGL
        a = Line3DCollectionGL([], c_data = c, gl_lighting = False,  **kywds)
        a._segments3d = (np.transpose(np.vstack((np.array(x), np.array(y), np.array(z)))),)
        a.convert_2dpath_to_3dpath()
        a.set_alpha(1.0)
        self.add_collection(a)
        return a

    def contour(self, *args, **kwargs):
        from art3d_gl import poly_collection_3d_to_gl 
        offset = kwargs['offset'] if 'offset' in kwargs else None
        zdir = kwargs['zdir'] if 'zdir' in kwargs else 'z'
        cset = Axes3D.contour(self, *args, **kwargs)
        for z, linec in zip(np.argsort(cset.levels), cset.collections) :
            convert_to_gl(linec)
            linec.convert_2dpath_to_3dpath(z, zdir = 'z')
            linec.do_stencil_test = True
            if offset is not None:
                if zdir == 'x': linec._gl_offset = (z*0.001, 0, 0)
                elif zdir == 'y': linec._gl_offset = (0, z*0.001, 0)
                else: linec._gl_offset = (0, 0, z*0.001)
        return cset

    def imshow(self, *args, **kwargs):
        im_center= kwargs.pop('im_center', (0,0))
        im_axes = kwargs.pop('im_axes', [(1, 0, 0), (0, 1, 0)])
                             
        from art3d_gl import image_to_gl         
        im = Axes3D.imshow(self, *args, **kwargs)
        image_to_gl(im)
        im.set_3dpath(im_center, im_axes)                     
        return im        

    def contourf(self, *args, **kwargs):
        from art3d_gl import poly_collection_3d_to_gl 
        offset = kwargs['offset'] if 'offset' in kwargs else None
        zdir = kwargs['zdir'] if 'zdir' in kwargs else 'z'
        cset = Axes3D.contourf(self, *args, **kwargs)
        edgecolor = kwargs.pop('edgecolor', [1,1,1,0])
        for z, linec in zip(np.argsort(cset.levels), cset.collections) :
            convert_to_gl(linec)
            linec.convert_2dpath_to_3dpath(z, zdir = 'z')
            linec.do_stencil_test = True
            if offset is not None:
                if zdir == 'x': linec._gl_offset = (z*0.001, 0, 0)
                elif zdir == 'y': linec._gl_offset = (0, z*0.001, 0)
                else: linec._gl_offset = (0, 0, z*0.001)
            linec.set_edgecolor((edgecolor,))
        return cset
    
    def quiver(self, *args, **kwargs):
        '''
         quiver(x, y, z, u, v, w, length=0.1, normalize = True, **kwargs)  

            kwargs: facecolor
                    edgecolor
                    alpha
                    cz, cdata
          
        '''
        # made based on mplot3d but makes GL solid object
        # handle kwargs
        # shaft length
        length = kwargs.pop('length', 1.0)
        # arrow length ratio to the shaft length 
        arrow_length_ratio = kwargs.pop('arrow_length_ratio', 0.3)
        # pivot point (not implemeted)
        pivot = kwargs.pop('pivot', 'tail')
        # normalize
        normalize = kwargs.pop('normalize', False)

        # handle args
        argi = 6
        if len(args) < argi:
            ValueError('Wrong number of arguments. Expected %d got %d' %
                       (argi, len(args)))

        # first 6 arguments are X, Y, Z, U, V, W
        input_args = args[:argi]
        # if any of the args are scalar, convert into list
        input_args = [[k] if isinstance(k, (int, float)) else k
                      for k in input_args]

        # extract the masks, if any
        masks = [k.mask for k in input_args if isinstance(k, np.ma.MaskedArray)]
        # broadcast to match the shape
        bcast = np.broadcast_arrays(*(input_args + masks))
        input_args = bcast[:argi]
        masks = bcast[argi:]
        if masks:
            # combine the masks into one
            mask = reduce(np.logical_or, masks)
            # put mask on and compress
            input_args = [np.ma.array(k, mask=mask).compressed()
                          for k in input_args]
        else:
            input_args = [k.flatten() for k in input_args]
        XYZ = np.column_stack(input_args[:3])
        UVW = np.column_stack(input_args[3:argi]).astype(float)

        norm = np.sqrt(np.sum(UVW**2, axis=1))            
        # If any row of UVW is all zeros, don't make a quiver for it
        mask = norm > 0
        norm = norm[mask]
        XYZ = XYZ[mask]
        ORT = UVW[mask] / norm.reshape((-1, 1))
        if normalize:
            norm = np.array([length]*len(ORT))
        else:
            norm = norm/np.max(norm)*length

        h = np.max(norm)*arrow_length_ratio
        r1 = kwargs.pop('shaftsize', 0.05)
        r2 = kwargs.pop('headsize', 0.25)                        

        m = 13
        sample_len = len(arrow3d(XYZ[0], r1, r2, ORT[0], norm[0], h, m = m, pivot = pivot))
        v = np.vstack([arrow3d(base, r1, r2, ort, l, h, m = m, pivot = pivot)
                       for base, ort, l in zip(XYZ, ORT, norm)],)
        cdata = kwargs.pop('facecolordata', None)
        if cdata is not None:
            cdata = np.transpose(np.vstack([cdata.flatten()]*sample_len)).flatten()
            kwargs['facecolordata'] = cdata

        return self.plot_solid(v, **kwargs)
    
    def plot_revolve(self, R, Z,  *args, **kwargs):
        '''
        revolve

        '''
        raxis = np.array(kwargs.pop('raxis', (0,  1)))
        rtheta = kwargs.pop('rtheta', (0, np.pi*2))
        rmesh =  kwargs.pop('rmesh', 30)
        rcenter =  np.array(kwargs.pop('rcenter', [0, 0]))
        theta = np.linspace(rtheta[0], rtheta[1], rmesh)

        pos = np.vstack((R-rcenter[0], Z-rcenter[1]))
        nraxis = raxis/np.sqrt(np.sum(raxis**2))
        nraxis = np.hstack([nraxis.reshape(2,-1)]*len(R))
        nc     = np.hstack([rcenter.reshape(2,-1)]*len(R))
        dcos = np.sum(pos*nraxis, 0) 
        newz = nc + dcos #center of rotation
        dsin = pos[0,:]*nraxis[1,:] - pos[1,:]*nraxis[0,:]

#        Theta, R = np.meshgrid(theta, np.abs(dsin))
#        void, Z = np.meshgrid(theta, dcos)
        R, Theta = np.meshgrid(np.abs(dsin), theta)
        Z, void = np.meshgrid(dcos, theta)

        X = R*np.cos(Theta)
        Y = R*np.sin(Theta)

        tt = np.pi/2-np.arctan2(raxis[1], raxis[0])
        m = np.array([[np.cos(tt),0, -np.sin(tt)],
                      [0, 1, 0],
                      [np.sin(tt),0, np.cos(tt)],])

        dd = np.dot(np.dstack((X, Y, Z)), m)
        X = dd[:,:,0]+rcenter[0]; Y = dd[:,:,1]; Z = dd[:,:,2] + rcenter[1]

#        from ifigure.interactive import figure
#        v = figure()
#        v.plot(X, Z)
        #facecolor = kwargs.pop('facecolor', (0,0,1,1))
        X, Y, Z = np.broadcast_arrays(X, Y, Z)

        polyc = self.plot_surface(X, Y, Z, *args, **kwargs)
        polyc._revolve_data = (X, Y, Z)
        return polyc
    
    def plot_extrude(self, X, Y, Z, path,
                     scale = None, revolve = False):
        '''
        extrude a path drawn by X, Y, Z along the path
            path.shape = [:, 3]

         A, B = np.meshgrid(ai, bj)
           A.shape = (j, i). A[j,i] = ai
           B.shape = (j, i). B[j,i] = bj

           X[j, i] = X[i] - path_x[0] + path_x[j]
           X.flatten() = X[0, :], X[1,:], X[2,:]
        '''
        facecolor = kwargs.pop('facecolor', (0,0,1,1))        
        scale = kwargs.pop('scale', 1.0)
        scale = kwargs.pop('scale', 1.0)        
        x1, x2  = np.meshgrid(path[:,0], X) ; x = x1 + x2 - path[0,0]
        y1, y2  = np.meshgrid(path[:,1], Y) ; y = y1 + y2 - path[0,1]
        z1, z2  = np.meshgrid(path[:,2], Z) ; z = z1 + z2 - path[0,2]

        X = x.flatten(); Y = y.flatten(); Z = z.flatten()
        polyc = self.plot_surface(X, Y, Z, *args, **kwargs)
        return polyc
        
    def plot_surface(self, X, Y, Z, *args, **kwargs):
        '''
        Create a surface plot using OpenGL-based artist

        By default it will be colored in shades of a solid color,
        but it also supports color mapping by supplying the *cmap*
        argument.

        ============= ================================================
        Argument      Description
        ============= ================================================
        *X*, *Y*, *Z* Data values as 2D arrays
        *edgecolor*   Color of the surface patches (default 'k')
        *facecolor*   Color of the surface patches (default None: use cmap)
        *rstride*     Reduce data 
        *cstride*     Reduce data 
        *cmap*        A colormap for the surface patches.
        *shade*       Whether to shade the facecolors
        ============= ================================================

        Other arguments are passed on to
        :class:`~mpl_toolkits.mplot3d.art3d.Poly3DCollection`
        '''
        cz = kwargs.pop('cz', False)
        cdata = kwargs.pop('cdata', None)        

        Z = np.atleast_2d(Z)
        # TODO: Support masked arrays
        if Y.ndim==1 and X.ndim ==1: X, Y = np.meshgrid(X, Y)
        X, Y, Z = np.broadcast_arrays(X, Y, Z)
        rows, cols = Z.shape

        rstride = kwargs.pop('rstride', 10)
        cstride = kwargs.pop('cstride', 10)
        idxset3d =[]
        r = list(xrange(0, rows, rstride))
        c = list(xrange(0, cols, cstride))

        X3D = X[r, :][:, c].flatten()
        Y3D = Y[r, :][:, c].flatten()
        Z3D = Z[r, :][:, c].flatten()

        ### array index
        idxset = []
        l_r = len(r); l_c = len(c)
#        offset = np.array([0, 1, l_c+1, l_c, 0])
        offset = np.array([0, 1, l_c+1, l_c])        
        base = np.arange(l_r*l_c).reshape(l_r, l_c)
        base = base[:-1, :-1].flatten()

        idxset = np.array([x + offset for x in base], 'H')

        #idxset = tri.get_masked_triangles()

        verts = np.dstack((X3D[idxset], 
                           Y3D[idxset],
                           Z3D[idxset]))
        if cz:
            if cdata is not None:
                cdata = cdata[r, :][:, c].flatten()[idxset]
            else:
                cdata = Z3D[idxset]
            shade = kwargs.pop('shade', 'flat')
            if shade != 'linear':
                cdata = np.mean(cdata, -1)
            kwargs['facecolordata'] = cdata.real
            kwargs.pop('facecolor', None) # get rid of this keyword

        kwargs['cz'] = cz

        return self.plot_solid(verts, **kwargs)

    def plot_trisurf(self, *args, **kwargs):
        '''
        plot_trisurf(x, y, z,  **wrargs)
        plot_trisurf(x, y, z,  triangles = triangle,,,)
        plot_trisurf(tri, z,  **kwargs, cz = cz, cdata = cdata)


        '''
        from art3d_gl import poly_collection_3d_to_gl
        from matplotlib.tri.triangulation import Triangulation

        cz = kwargs.pop('cz', False)
        cdata = kwargs.pop('cdata', None)        
        tri, args, kwargs = Triangulation.get_from_args_and_kwargs(*args, **kwargs)
        if 'Z' in kwargs:
            z = np.asarray(kwargs.pop('Z'))
        else:
            z = np.asarray(args[0])
            # We do this so Z doesn't get passed as an arg to PolyCollection
            args = args[1:]

        triangles = tri.get_masked_triangles()
        X3D = tri.x
        Y3D = tri.y
        Z3D = z
        idxset = tri.get_masked_triangles()

        verts = np.dstack((X3D[idxset], 
                           Y3D[idxset],
                           Z3D[idxset]))
        if cz:
            if cdata is not None:
                cdata = cdata[idxset]
            else:
                cdata = Z3D[idxset]
            shade = kwargs.pop('shade', 'flat')
            if shade != 'linear':
                cdata = np.mean(cdata, -1)
            kwargs['facecolordata'] = cdata.real
            kwargs.pop('facecolor', None) # get rid of this keyword

        kwargs['cz'] = cz

        return self.plot_solid(verts, **kwargs)
    
    def plot_solid(self, v, **kwargs):
        '''
        v [element_index, points_in_element, xyz]

        kwargs: normals : normal vectors
        '''
        #gl_3dpath = kwargs.get('gl_3dpath', None)
        
        norms = kwargs.pop('normals', None)        
        if norms is None:
            norms = []
            for xyz in v:
                if xyz.shape[0] > 2:
                    p0, p1, p2 = [xyz[k,:3] for k in range(3)]
                    n1 = np.cross(p0-p1, p1-p2)
                    d = np.sqrt(np.sum(n1**2))
                else:
                    d = 0
                if d == 0:
                    norms.append([0,0,1]*xyz.shape[0])
                else:
                    norms.extend([-n1/d]*xyz.shape[0])
            norms = np.hstack(norms).astype(np.float32).reshape(-1,3)
        nv = len(v[:, :, 2].flatten())
        kwargs['gl_3dpath'] = [v[:, :, 0].flatten(),
                               v[:, :, 1].flatten(),
                               v[:, :, 2].flatten(),
                               norms,
                               np.arange(nv).reshape(v.shape[0], v.shape[1])]
        
        from art3d_gl import Poly3DCollectionGL
        a = Poly3DCollectionGL(v, **kwargs)
        Axes3D.add_collection3d(self, a)
        a.do_stencil_test = False

        return a

    def get_proj2(self):
        '''
        based on mplot3d::get_proj()
        it exposes matries used to compose projection matrix,
        and supports orthogonal projection.
        '''
        relev, razim = np.pi * self.elev/180, np.pi * self.azim/180

        xmin, xmax = self.get_xlim3d()
        ymin, ymax = self.get_ylim3d()
        zmin, zmax = self.get_zlim3d()

        # transform to uniform world coordinates 0-1.0,0-1.0,0-1.0
        worldM = proj3d.world_transformation(xmin, xmax,
                                             ymin, ymax,
                                             zmin, zmax)
        # look into the middle of the new coordinates
        R = np.array([0.5, 0.5, 0.5])

        xp = R[0] + np.cos(razim) * np.cos(relev) * self.dist
        yp = R[1] + np.sin(razim) * np.cos(relev) * self.dist
        zp = R[2] + np.sin(relev) * self.dist
        E = np.array((xp, yp, zp))

        self.eye = E
        self.vvec = R - E
        self.vvec = self.vvec / proj3d.mod(self.vvec)

        if abs(relev) > np.pi/2:
            V = np.array((0, 0, -1))
        else:
            V = np.array((0, 0, 1))
        V = self._upvec            
        zfront, zback = -self.dist, self.dist
        #zfront, zback = self.dist-1, self.dist+1

        viewM = proj3d.view_transformation(E, R, V)
        if self._use_frustum:
           perspM = proj3d.persp_transformation(zfront, zback)
        else:
           a = (zfront+zback)/(zfront-zback)            
           b = -2*(zfront*zback)/(zfront-zback)            
           perspM = np.array([[1,0,0,0],
                             [0,1,0,0],
                             [0,0,a,b],
                             [0,0,-1/10000.,self.dist]
                              ])
        return  worldM, viewM, perspM, E, R, V, self.dist
    
    def get_proj(self):
        worldM, viewM, perspM, E, R, V, self.dist = self.get_proj2()
        M0 = np.dot(viewM, worldM)
        M = np.dot(perspM, M0)
        return M            

    def set_lighting(self, *args, **kwargs):
        if len(args) != 0:
            kwargs =  args[0]
        for k in kwargs:
            if k in self._lighting:
                self._lighting[k] = kwargs[k]
    def get_lighting(self):
        return self._lighting

    def show_3d_axes(self, value):
        self._show_3d_axes = value
        
    def draw_3d_axes(self):
        M  = self.get_proj()
        dx = self.get_xlim()
        dy = self.get_ylim()
        dz = self.get_zlim()        
        xvec = np.dot(M, np.array([abs(dx[1]-dx[0]),0,0,0]))[:2]
        yvec = np.dot(M, np.array([0, abs(dy[1]-dy[0]),0,0]))[:2]
        zvec = np.dot(M, np.array([0,0,abs(dz[1]-dz[0]),0]))[:2]
    
        po = self.transAxes.transform([0.1, 0.1])
        pod = self.transData.transform([0.0, 0.0])
        fac = np.sqrt(np.sum((xvec-pod)**2 + (yvec-pod)**2 + (zvec-pod)**2))/5.

        tt = self.transData.inverted()
        def ptf(x):
            pp = self.transData.transform(x)
            st =  tt.transform(po)
            et =  tt.transform((pp-pod)/fac+po)
            et2 =  tt.transform(1.5*(pp-pod)/fac+po)            
            return [st[0], et[0]], [st[1], et[1]] , et2
        
        if self._3d_axes_icon is None:
            p0, p1, pt = ptf(xvec)
            a1 = Line2D(p0, p1,
                        color='r', axes=self, figure=self.figure)
            a4 = Text(pt[0], pt[1], 'x', color='r',
                      axes=self, figure=self.figure,
                      transform = self.transData,
                      verticalalignment='center',
                      horizontalalignment='center')
            
            p0, p1, pt = ptf(yvec); 
            a2 = Line2D(p0, p1,
                        color='g', axes=self, figure=self.figure)
            a5 = Text(pt[0], pt[1], 'y', color='g',
                      axes=self, figure=self.figure,
                      transform = self.transData,
                      verticalalignment='center',
                      horizontalalignment='center')
            
            p0, p1, pt = ptf(zvec); 
            a3 = Line2D(p0, p1,
                        color='b', axes=self, figure=self.figure)
            a6 = Text(pt[0], pt[1], 'z', color='b',
                      axes=self, figure=self.figure,
                      transform = self.transData,
                      verticalalignment='center',
                      horizontalalignment='center')
            
            self.add_line(a1)
            self.add_line(a2)
            self.add_line(a3)
            self.texts.append(a4)
            self.texts.append(a5)
            self.texts.append(a6)            
            self._3d_axes_icon = [weakref.ref(a1),
                                  weakref.ref(a2),
                                  weakref.ref(a3),
                                  weakref.ref(a4),
                                  weakref.ref(a5),
                                  weakref.ref(a6)]
        else:
            p0, p1, pt = ptf(xvec)            
            self._3d_axes_icon[0]().set_xdata(p0)
            self._3d_axes_icon[0]().set_ydata(p1)
            self._3d_axes_icon[3]().set_x(pt[0])
            self._3d_axes_icon[3]().set_y(pt[1])
            
            p0, p1, pt = ptf(yvec)            
            self._3d_axes_icon[1]().set_xdata(p0)
            self._3d_axes_icon[1]().set_ydata(p1)
            self._3d_axes_icon[4]().set_x(pt[0])
            self._3d_axes_icon[4]().set_y(pt[1])
            
            p0, p1, pt = ptf(zvec)            
            self._3d_axes_icon[2]().set_xdata(p0)
            self._3d_axes_icon[2]().set_ydata(p1)
            self._3d_axes_icon[5]().set_x(pt[0])
            self._3d_axes_icon[5]().set_y(pt[1])

    @allow_rasterization
    def draw(self, renderer):
        self.patch.set_facecolor(self.figure.patch.get_facecolor())

#        if self._use_gl and isSupportedRenderer(renderer):
        gl_len = 0
        if isSupportedRenderer(renderer):    
            self._matrix_cache = self.get_proj2()
            artists = []

            artists.extend(self.images)
            artists.extend(self.collections)
            artists.extend(self.patches)
            artists.extend(self.lines)
            artists.extend(self.texts)
            artists.extend(self.artists)
            gl_obj = [a for a in artists if hasattr(a, 'is_gl')]

            gl_len = len(gl_obj)
            if gl_obj > 0:
                glcanvas = get_glcanvas()
                if (glcanvas is not None and
                    glcanvas.init): 
                    glcanvas.set_lighting(**self._lighting)
                else: 
                    return
            renderer._num_globj = gl_len
            renderer._k_globj =   0
                
        ### axes3D seems to change frameon status....
        frameon = self.get_frame_on()
        self.set_frame_on(False)
        if self._show_3d_axes:
            self.draw_3d_axes()
            for a in self._3d_axes_icon: a().set_zorder(gl_len+1)
        else:
            if self._3d_axes_icon is not None:
                self.lines.remove(self._3d_axes_icon[0]())
                self.lines.remove(self._3d_axes_icon[1]())
                self.lines.remove(self._3d_axes_icon[2]())
                self.texts.remove(self._3d_axes_icon[3]())
                self.texts.remove(self._3d_axes_icon[4]())
                self.texts.remove(self._3d_axes_icon[5]())                
            self._3d_axes_icon  = None

        val = Axes3D.draw(self, renderer)
        self.set_frame_on(frameon)
        return val





