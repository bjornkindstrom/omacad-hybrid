mod bvh;
use bvh::{Bvh, Triangle};
use pyo3::{exceptions::PyValueError, prelude::*, types::PyBytes};

/// Owns a snapshot of immutable mesh data: no NumPy pointer survives a Python call.
#[pyclass(frozen)]
struct TriangleIndex {
    tree: Bvh,
}
fn validate_ray(origin: [f64; 3], direction: [f64; 3], tolerance: f64) -> PyResult<()> {
    if !origin.iter().chain(direction.iter()).all(|v| v.is_finite()) || !tolerance.is_finite() {
        return Err(PyValueError::new_err("ray and tolerance must be finite"));
    }
    Ok(())
}
#[pymethods]
impl TriangleIndex {
    #[new]
    fn new(py: Python<'_>, triangles: &[u8], owners: &[u8], face_count: usize) -> PyResult<Self> {
        if triangles.len() % 72 != 0
            || owners.len() / 4 != triangles.len() / 72
            || owners.len() % 4 != 0
        {
            return Err(PyValueError::new_err(
                "expected (N,3,3) little-endian float64 triangles and N uint32 face owners",
            ));
        }
        // Copy once at mesh construction, then build without holding Python's GIL.
        let mut data = Vec::with_capacity(triangles.len() / 72);
        for (index, bytes) in triangles.chunks_exact(72).enumerate() {
            let mut vertices = [[0.0; 3]; 3];
            for (dst, src) in vertices.iter_mut().flatten().zip(bytes.chunks_exact(8)) {
                *dst = f64::from_le_bytes(src.try_into().unwrap());
            }
            let owner =
                u32::from_le_bytes(owners[index * 4..index * 4 + 4].try_into().unwrap()) as usize;
            if owner >= face_count || !vertices.iter().flatten().all(|v| v.is_finite()) {
                return Err(PyValueError::new_err(
                    "non-finite vertex or out-of-range face owner",
                ));
            }
            data.push(Triangle {
                vertices,
                owner,
                index,
            });
        }
        Ok(Self {
            tree: py.detach(move || Bvh::new(data, face_count)),
        })
    }
    #[pyo3(signature=(origin,direction,bary_tol=1e-9))]
    fn face_hits<'py>(
        &self,
        py: Python<'py>,
        origin: [f64; 3],
        direction: [f64; 3],
        bary_tol: f64,
    ) -> PyResult<Bound<'py, PyBytes>> {
        validate_ray(origin, direction, bary_tol)?;
        let hits = py.detach(|| self.tree.face_hits(origin, direction, bary_tol));
        let bytes: Vec<u8> = hits.iter().flat_map(|v| v.to_le_bytes()).collect();
        Ok(PyBytes::new(py, &bytes))
    }
    #[pyo3(signature=(origin,direction,bary_tol=1e-9))]
    fn nearest(
        &self,
        py: Python<'_>,
        origin: [f64; 3],
        direction: [f64; 3],
        bary_tol: f64,
    ) -> PyResult<Option<(f64, usize)>> {
        validate_ray(origin, direction, bary_tol)?;
        Ok(py.detach(|| self.tree.nearest(origin, direction, bary_tol)))
    }
    #[getter]
    fn triangle_count(&self) -> usize {
        self.tree.triangle_count()
    }
}
#[pymodule]
fn _viewport_native(module: &Bound<'_, PyModule>) -> PyResult<()> {
    module.add_class::<TriangleIndex>()?;
    module.add("API_VERSION", 1)?;
    Ok(())
}
