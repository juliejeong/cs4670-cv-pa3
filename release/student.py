# Please place imports here.
# BEGIN IMPORTS
import numpy as np
import cv2
import scipy
from scipy import ndimage
# END IMPORTS


def compute_photometric_stereo_impl(lights, images):
    """
    Given a set of images taken from the same viewpoint and a corresponding set
    of directions for light sources, this function computes the albedo and
    normal map of a Lambertian scene.

    If the computed albedo for a pixel has an L2 norm less than 1e-7, then set
    the albedo to black and set the normal to the 0 vector.

    Normals should be unit vectors.

    Input:
        lights -- 3 x N array.  Each column is a unit vector representing a 
                  light source and its orientation in all three axes.
        images -- list of N images.  Each image is of the same scene from the
                  same viewpoint, but under the lighting condition specified in
                  lights.
    Output:
        albedo -- float32 height x width x channels image with dimensions
                  matching the input images.
        normals -- float32 height x width x 3 image with dimensions matching
                   the input images.
    """
    img_shape = images[0].shape
    n = len(images)

    I = np.zeros((img_shape[0], img_shape[1], n))
    I = np.dstack([images[i][:, :, 0] for i in range(n)])

    G = np.matmul(np.matmul(I, np.transpose(lights)), np.linalg.inv(
        np.matmul(lights, np.transpose(lights))))

    kd = np.linalg.norm(G, axis=2)
    kd = np.where(kd == 0, 1e-7, kd)
    normals = G / kd[:, :, np.newaxis]
    normals[kd == 0] = 0

    num = np.zeros(img_shape)
    den = np.zeros(img_shape)

    for j in range(n):
        currChannel = images[j]

        num += np.dot(normals, lights[:, j])[..., np.newaxis] * currChannel
        den += np.square(np.dot(normals, lights[:, j]))[..., np.newaxis]

    den[den == 0] = 1
    albedo = np.divide(num, den, where=den > 0)

    mask = np.linalg.norm(albedo, axis=2) < 1e-7
    albedo[mask] = 0
    normals[mask] = 0

    return albedo.astype(np.float32), normals.astype(np.float32)


def pyrdown_impl(image):
    """
    Prefilters an image with a gaussian kernel and then downsamples the result
    by a factor of 2.

    The following 1D convolution kernel should be used in both the x and y
    directions.
    K = 1/16 [ 1 4 6 4 1 ]

    Functions such as cv2.GaussianBlur and scipy.ndimage.gaussian_filter are
    prohibited.  You must implement the separable kernel.  However, you may
    use functions such as cv2.filter2D or scipy.ndimage.correlate to do the actual
    correlation / convolution. Note that for images with one channel, cv2.filter2D
    will discard the channel dimension so add it back in.

    Filtering should mirror the input image across the border.
    For scipy this is mode = mirror.
    For cv2 this is mode = BORDER_REFLECT_101.

    Downsampling should take the even-numbered coordinates with coordinates
    starting at 0.

    Input:
        image -- height x width x channels image of type float32.
    Output:
        down -- ceil(height/2) x ceil(width/2) x channels image of type
                float32.
    """
    K = np.array([1, 4, 6, 4, 1]) / 16.0

    img_filt = cv2.filter2D(
        image, -1, K[:, np.newaxis], borderType=cv2.BORDER_REFLECT_101)
    img_filt = cv2.filter2D(img_filt, -1, K[:, np.newaxis].transpose(),
                            borderType=cv2.BORDER_REFLECT_101)

    down = img_filt[::2, ::2]

    if down.ndim == 2:
        down = down[..., np.newaxis]

    return down


def pyrup_impl(image):
    """
    Upsamples an image by a factor of 2 and then uses a gaussian kernel as a
    reconstruction filter.

    The following 1D convolution kernel should be used in both the x and y
    directions.
    K = 1/8 [ 1 4 6 4 1 ]
    Note: 1/8 is not a mistake.  The additional factor of 4 (applying this 1D
    kernel twice) scales the solution according to the 2x2 upsampling factor.

    Filtering should mirror the input image across the border.
    For scipy this is mode = mirror.
    For cv2 this is mode = BORDER_REFLECT_101.

    Upsampling should produce samples at even-numbered coordinates with
    coordinates starting at 0.

    Input:
        image -- height x width x channels image of type float32.
    Output:
        up -- 2*height x 2*width x channels image of type float32.
    """
    img_shape = image.shape

    new_shape = (2 * img_shape[0], 2 * img_shape[1])
    if len(img_shape) == 2:
        new_shape += (1,)
    else:
        new_shape += (img_shape[2],)

    new_img = np.zeros(new_shape)
    new_img[::2, ::2] = image

    K = np.array([1.0, 4.0, 6.0, 4.0, 1.0]) / 8.0
    # K = np.reshape(K, (-1, 1))
    img_filt = cv2.filter2D(
        new_img, -1, K[:, np.newaxis], borderType=cv2.BORDER_REFLECT_101)
    img_filt = cv2.filter2D(img_filt, -1, K[:, np.newaxis].transpose(),
                            borderType=cv2.BORDER_REFLECT_101)

    if img_filt.ndim == 2:
        img_filt = img_filt[..., np.newaxis]

    return img_filt


# vectorize to improve run time
def project_impl(K, Rt, points):
    """
    Project 3D points into a calibrated camera.

    Input:
        K -- camera intrinsics calibration matrix
        Rt -- 3 x 4 camera extrinsics calibration matrix
        points -- height x width x 3 array of 3D points
    Output:
        projections -- height x width x 2 array of 2D projections
    """
    height, width, _ = np.shape(points)
    proj = np.zeros((height, width, 2))

    for i in range(height):
        for j in range(width):
            location = np.matmul(K, np.matmul(Rt, np.append(points[i, j], 1)))

            if location[2] >= 1e-7:
                proj[i, j] = location[:2] / location[2]

    return proj


def unproject_corners_impl(K, width, height, depth, Rt):
    """
    Undo camera projection given a calibrated camera and the depth for each
    corner of an image.

    The output points array is a 2x2x3 array arranged for these image
    coordinates in this order:

     (0, 0)      |  (width, 0)
    -------------+------------------
     (0, height) |  (width, height)

    Each of these contains the 3 vector for the corner's corresponding
    point in 3D.

    Tutorial:
      Say you would like to unproject the pixel at coordinate (x, y)
      onto a plane at depth z with camera intrinsics K and camera
      extrinsics Rt.

      (1) Convert the coordinates from homogeneous image space pixel
          coordinates (2D) to a local camera direction (3D):
          (x', y', 1) = K^-1 * (x, y, 1)
      (2) This vector can also be interpreted as a point with depth 1 from
          the camera center.  Multiply it by z to get the point at depth z
          from the camera center.
          (z * x', z * y', z) = z * (x', y', 1)
      (3) Use the inverse of the extrinsics matrix, Rt, to move this point
          from the local camera coordinate system to a world space
          coordinate.
          Note:
            | R t |^-1 = | R^T -R^T t |
            | 0 1 |      | 0      1   |

          p = R^T * (z * x', z * y', z) - R^T t

    Input:
        K -- camera intrinsics calibration matrix
        width -- camera width
        height -- camera height
        depth -- depth of plane with respect to camera
        Rt -- 3 x 4 camera extrinsics calibration matrix
    Output:
        points -- 2 x 2 x 3 array of 3D points
    """
    corners = np.array([[0., 0., 1.], [width*1., 0., 1.],
                       [0., height*1., 1.], [width*1., height*1., 1.]]).reshape(2, 2, 3)
    # corners = np.matmul(np.linalg.inv(K), corners.reshape(
    #     4, 3, 1)).reshape(2, 2, 3) * depth
    corners = np.tensordot(corners, np.linalg.inv(K).T, axes=1)
    corners = corners * depth
    # R = np.zeros((4, 3))
    # t = np.ones((4, 1))

    R = Rt[:3, :3]
    t = Rt[:3, 3]

    corners = np.tensordot(corners, R, axes=1)
    corners = corners - R.T.dot(t)

    # corners_mod = np.full((2, 2, 4), 1)
    # corners_mod[..., :3] = corners[..., :3]

    # for i, j in np.ndindex(corners.shape[:2]):
    #     corners_ij = corners_mod[i, j, np.newaxis].T
    #     corners[i, j] = ((R.T).dot(corners_ij) - (R.T).dot(t))[:, 0]

    return corners


def preprocess_ncc_impl(image, ncc_size):
    """
    Prepare normalized patch vectors according to normalized cross
    correlation.

    This is a preprocessing step for the NCC pipeline.  It is expected that
    'preprocess_ncc' is called on every input image to preprocess the NCC
    vectors and then 'compute_ncc' is called to compute the dot product
    between these vectors in two images.

    NCC preprocessing has two steps.
    (1) Compute and subtract the mean.
    (2) Normalize the vector.

    The mean is per channel.  i.e. For an RGB image, over the ncc_size**2
    patch, compute the R, G, and B means separately.  The normalization
    is over all channels.  i.e. For an RGB image, after subtracting out the
    RGB mean, compute the norm over the entire (ncc_size**2 * channels)
    vector and divide.

    If the norm of the vector is < 1e-6, then set the entire vector for that
    patch to zero.

    Patches that extend past the boundary of the input image at all should be
    considered zero.  Their entire vector should be set to 0.

    Patches are to be flattened into vectors with the default numpy row
    major order.  For example, given the following
    2 (height) x 2 (width) x 2 (channels) patch, here is how the output
    vector should be arranged.

    channel1         channel2
    +------+------+  +------+------+ height
    | x111 | x121 |  | x112 | x122 |  |
    +------+------+  +------+------+  |
    | x211 | x221 |  | x212 | x222 |  |
    +------+------+  +------+------+  v
    width ------->

    v = [ x111, x121, x211, x221, x112, x122, x212, x222 ]

    Input:
        image -- height x width x channels image of type float32
        ncc_size -- integer width and height of NCC patch region.
    Output:
        normalized -- heigth x width x (channels * ncc_size**2) array
    """
    img_shape = image.shape
    ans = np.zeros([img_shape[0], img_shape[1],
                   img_shape[2] * ncc_size * ncc_size])
    low = - (ncc_size // 2)
    high = ncc_size // 2

    for y in range(img_shape[0]):
        for x in range(img_shape[1]):
            condition = (
                y + low >= 0 and
                x + low >= 0 and
                y + high < img_shape[0] and
                x + high < img_shape[1]
            )

            if condition:
                for k in range(img_shape[2]):
                    patch = image[y + low: y + high +
                                  1, x + low: x + high + 1, k]
                    flat_patch = patch.reshape(-1)
                    start = k * ncc_size * ncc_size
                    end = (k + 1) * ncc_size * ncc_size
                    ans[y, x, start:end] = np.asarray(flat_patch)

    ans -= np.mean(ans, axis=2)[:, :, np.newaxis]

    norm = np.linalg.norm(ans, axis=2)[:, :, np.newaxis]
    norm[norm == 0] = 1
    ans /= norm

    return ans


def compute_ncc_impl(image1, image2):
    """
    Compute normalized cross correlation between two images that already have
    normalized vectors computed for each pixel with preprocess_ncc.

    Input:
        image1 -- height x width x (channels * ncc_size**2) array
        image2 -- height x width x (channels * ncc_size**2) array
    Output:
        ncc -- height x width normalized cross correlation between image1 and
               image2.
    """

    return np.sum(image1 * image2, axis=2)
