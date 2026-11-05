"""Plate proposals shared by photos and live/video frames, including bus/bike crop retry."""
def detect_plate_candidates(detector, frame, vehicles, confidence, max_roi_retries=4, retry_offset=0):
    boxes=[tuple(v['bbox']) for v in vehicles]
    detections=detector.detect_in_frame(frame,vehicle_boxes=boxes or None,conf_thresh=confidence)
    matched={tuple(p['vehicle_bbox']) for p in detections if p.get('vehicle_bbox')}
    height,width=frame.shape[:2]
    missing=[v for v in vehicles if tuple(v['bbox']) not in matched]
    # Give two-wheelers and buses first access to bounded crop-level retries.
    missing.sort(key=lambda v: (not any(word in str(v.get('cls_name','')).lower().replace('_',' ') for word in ('motor','bike','bicycle','two wheeler','bus')), (v['bbox'][2]-v['bbox'][0])*(v['bbox'][3]-v['bbox'][1])))
    if missing:
        offset = retry_offset % len(missing)
        missing = missing[offset:] + missing[:offset]
    for vehicle in missing[:max_roi_retries]:
        vx1,vy1,vx2,vy2=map(int,vehicle['bbox'])
        vw,vh=vx2-vx1,vy2-vy1
        if vw<24 or vh<24:continue
        x1=max(0,vx1-int(vw*.05));y1=max(0,vy1-int(vh*.05))
        x2=min(width,vx2+int(vw*.05));y2=min(height,vy2+int(vh*.05))
        crop=frame[y1:y2,x1:x2]
        if not crop.size:continue
        for proposal in detector.detect_in_frame(crop,conf_thresh=confidence):
            px1,py1,px2,py2=proposal['bbox']
            box=(max(0,x1+int(px1)),max(0,y1+int(py1)),min(width,x1+int(px2)),min(height,y1+int(py2)))
            cx,cy=(box[0]+box[2])/2,(box[1]+box[3])/2
            if not(vx1<=cx<=vx2 and vy1<=cy<=vy2):continue
            if box[2]<=box[0] or box[3]<=box[1]:continue
            detections.append({'bbox':box,'conf':proposal['conf'],'vehicle_bbox':tuple(vehicle['bbox'])})
    # The full frame and crop retries can find the same physical plate on overlapping tracks.
    # Keep one proposal per plate so a rider/bicycle/motorcycle overlap does not create two reads.
    unique=[]
    for detection in sorted(detections,key=lambda p:p.get('conf',0),reverse=True):
        a=detection['bbox']
        duplicate=False
        for kept in unique:
            b=kept['bbox']
            overlap=max(0,min(a[2],b[2])-max(a[0],b[0]))*max(0,min(a[3],b[3])-max(a[1],b[1]))
            union=max(1,(a[2]-a[0])*(a[3]-a[1])+(b[2]-b[0])*(b[3]-b[1])-overlap)
            if overlap/union>=.5:
                duplicate=True;break
        if not duplicate:unique.append(detection)
    return unique
