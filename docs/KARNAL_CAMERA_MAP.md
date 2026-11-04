# Karnal camera registry

The shared ICCC-KNL Google My Maps export supplies 62 sites and installed counts
totalling 391 cameras. Each device receives a stable local ID such as
`KNL-ICCC-001-C02` and the display name `Aggi Park 2`. Site serial numbers from
the source map form the ID; names can change without changing the site identity.

The map supplies **site** coordinates and aggregate working counts, not individual
camera directions, RTSP URLs, device identifiers or individual working status.
All numbered cameras at one site share its coordinates. Numbering is a local
convention and must be matched to actual devices when connecting feeds.

`resources/karnal_cameras.json` is the common registry, served at
`GET /api/cameras/registry`. The UI uses it for live feed selection, single and
batch uploads, camera filtering and trail mapping. Uploads require an explicit
camera selection; batch files never receive a guessed location. Live preview
slots CAM-01..04 remain separate from persistent numbered camera identities.
Trail writes resolve the selected name/ID to canonical GPS, camera ID and Karnal
district, including when the same camera is assigned to another preview slot.

Camera Map shows all sites. Click a site to select one of its numbered cameras.
Master Trail passage history shows registered-camera sightings on a map sorted
by evidence capture time, with a textual sequence for cameras sharing coordinates.
Dashed connections indicate observation order and do not establish a travelled
road route. Existing upload routing suggestions are estimates, not route evidence.

The source is a local snapshot, not a live Google Maps synchronization. To refresh:

```powershell
Invoke-WebRequest 'https://www.google.com/maps/d/kml?mid=1gn6Qrd9tdUrizJitDeGZDEjg6HOnHEI&forcekml=1' -OutFile data/karnal-cameras-source.kml
python scripts/import_camera_map.py data/karnal-cameras-source.kml
```

Restart the server after refreshing. Existing historical records are not renamed
or assigned to a different camera automatically. User/watchlist addresses and
case locations describe people or incidents; they are not overwritten with
camera coordinates.
