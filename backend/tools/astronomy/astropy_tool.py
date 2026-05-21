"""General-purpose Astropy computations exposed as one tool."""

from __future__ import annotations

import math
from typing import Any, ClassVar, Literal

import astropy.units as u
from astropy.coordinates import SkyCoord
from pydantic import BaseModel, Field
from pydantic import ValidationError as PydanticValidationError

from core.exceptions import ToolError
from tools.base_tool import BaseTool

AstropyOperation = Literal[
    "coord_convert",
    "ang_separation",
    "redshift_to_velocity",
    "wavelength_to_frequency",
    "magnitude_to_flux",
]


class AstropyInput(BaseModel):
    operation: AstropyOperation
    params: dict[str, Any] = Field(default_factory=dict)


class _CoordConvertParams(BaseModel):
    ra_deg: float
    dec_deg: float
    from_frame: str = "icrs"
    to_frame: str


class _AngSeparationParams(BaseModel):
    ra1_deg: float
    dec1_deg: float
    ra2_deg: float
    dec2_deg: float


class _RedshiftToVelocityParams(BaseModel):
    z: float
    model: Literal["non_relativistic", "relativistic"] = "relativistic"


class _WavelengthToFrequencyParams(BaseModel):
    wavelength: float
    unit: Literal["nm", "angstrom", "micron", "m"] = "nm"


class _MagnitudeToFluxParams(BaseModel):
    magnitude: float
    # AB magnitude default; override for Vega-band etc.
    zero_point_jy: float = 3631.0


class AstropyTool(BaseTool):
    """Coordinate conversions, angular separation, unit math via Astropy."""

    name: ClassVar[str] = "astropy_compute"
    description: ClassVar[str] = (
        "Astronomical computations via Astropy: coordinate frame conversion, "
        "angular separation, redshift / velocity, wavelength / frequency, "
        "magnitude / flux."
    )
    input_schema: ClassVar[type[BaseModel]] = AstropyInput

    async def execute(self, **kwargs: Any) -> dict[str, Any]:
        operation: AstropyOperation = kwargs["operation"]
        params: dict[str, Any] = kwargs.get("params") or {}
        handler = {
            "coord_convert": self._coord_convert,
            "ang_separation": self._ang_separation,
            "redshift_to_velocity": self._redshift_to_velocity,
            "wavelength_to_frequency": self._wavelength_to_frequency,
            "magnitude_to_flux": self._magnitude_to_flux,
        }[operation]
        return handler(params)

    def _coord_convert(self, params: dict[str, Any]) -> dict[str, Any]:
        p = self._validate(_CoordConvertParams, params, "coord_convert")
        coord = SkyCoord(ra=p.ra_deg * u.deg, dec=p.dec_deg * u.deg, frame=p.from_frame)
        try:
            converted = coord.transform_to(p.to_frame)
        except Exception as exc:
            # AltAz needs observer info; others may be unsupported.
            raise ToolError(
                message=f"Cannot transform from {p.from_frame!r} to {p.to_frame!r}: {exc}",
                code="astropy_unsupported_frame",
            ) from exc
        # spherical_representation gives stable lon/lat regardless of frame.
        rep = converted.spherical
        return {
            "from_frame": p.from_frame,
            "to_frame": p.to_frame,
            "longitude_deg": float(rep.lon.to(u.deg).value),
            "latitude_deg": float(rep.lat.to(u.deg).value),
        }

    def _ang_separation(self, params: dict[str, Any]) -> dict[str, Any]:
        p = self._validate(_AngSeparationParams, params, "ang_separation")
        c1 = SkyCoord(ra=p.ra1_deg * u.deg, dec=p.dec1_deg * u.deg, frame="icrs")
        c2 = SkyCoord(ra=p.ra2_deg * u.deg, dec=p.dec2_deg * u.deg, frame="icrs")
        sep = c1.separation(c2)
        return {
            "separation_deg": float(sep.to(u.deg).value),
            "separation_arcsec": float(sep.to(u.arcsec).value),
        }

    def _redshift_to_velocity(self, params: dict[str, Any]) -> dict[str, Any]:
        p = self._validate(_RedshiftToVelocityParams, params, "redshift_to_velocity")
        c_km_s = 299792.458
        if p.model == "non_relativistic":
            v = c_km_s * p.z
        else:
            zp1_sq = (1.0 + p.z) ** 2
            v = c_km_s * (zp1_sq - 1.0) / (zp1_sq + 1.0)
        return {"velocity_km_s": v, "model": p.model}

    def _wavelength_to_frequency(self, params: dict[str, Any]) -> dict[str, Any]:
        p = self._validate(_WavelengthToFrequencyParams, params, "wavelength_to_frequency")
        unit_map = {"nm": u.nm, "angstrom": u.AA, "micron": u.um, "m": u.m}
        wavelength = p.wavelength * unit_map[p.unit]
        frequency = wavelength.to(u.Hz, equivalencies=u.spectral())
        return {
            "wavelength": p.wavelength,
            "wavelength_unit": p.unit,
            "frequency_hz": float(frequency.value),
        }

    def _magnitude_to_flux(self, params: dict[str, Any]) -> dict[str, Any]:
        p = self._validate(_MagnitudeToFluxParams, params, "magnitude_to_flux")
        flux_jy = p.zero_point_jy * math.pow(10.0, -p.magnitude / 2.5)
        return {
            "magnitude": p.magnitude,
            "zero_point_jy": p.zero_point_jy,
            "flux_jy": flux_jy,
        }

    @staticmethod
    def _validate(
        schema: type[BaseModel],
        params: dict[str, Any],
        operation: str,
    ) -> Any:
        """Validate per-op params; raise ToolError on failure."""
        try:
            return schema(**params)
        except PydanticValidationError as exc:
            raise ToolError(
                message=f"Invalid params for operation {operation!r}",
                code="astropy_invalid_params",
                details={"errors": exc.errors()},
            ) from exc
