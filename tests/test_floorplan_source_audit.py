import gzip,hashlib,json
import pytest
from models.floorplan_source_audit import floorplan_metadata,body_references,checked_body


def test_only_explicit_floorplan_collection_labels_asset():
    assert floorplan_metadata({'media':{'photos':[{'key':'floor_plan_photo'}]}})['references']==[]
    r=floorplan_metadata({'media':{'floorPlans':[{'key':'asset123'}],'photos':[{'key':'other'}]}})
    assert r['references']==[{'asset_id':'asset123','source_path':'/media/floorPlans/0/key','explicit_floorplan_label':'media.floorPlans','raw_metadata':{'key':'asset123'}}]


def test_unresolved_metadata_does_not_imply_absence_of_actual_floorplan():
    assert floorplan_metadata({'media':{'floorPlans':'$123'}})['status']=='floorPlans_field_not_list'
    assert floorplan_metadata({'media':{'floorPlans':[]}})['status']=='empty_floorPlans_list'


def test_html_requires_explicit_label_and_same_raw_asset_key():
    body=b'<img alt="floor plan 1" src="https://photos.example/fp/abc-full.webp"><img alt="photo" src="https://photos.example/fp/abc-other.webp"><img alt="floor plan 2" src="https://photos.example/fp/other-full.webp">'
    refs=body_references(body,['abc'])
    assert len(refs)==1 and refs[0]['image_url']=='https://photos.example/fp/abc-full.webp'
    assert body_references(body,['missing'])==[]


def test_flight_gallery_explicit_type_and_exact_urls_are_retained():
    gallery={'description':'floor plan1','mediaType':'floor_plan','id':'8','mediaSrc':{'full':'https://photos.example/fp/abc-full.webp','small':'https://photos.example/fp/abc-small.webp'}}
    record='1:'+json.dumps(gallery)+'\n'
    body=('<script>self.__next_f.push('+json.dumps([1,record])+')</script>').encode()
    refs=body_references(body,['abc'])
    assert len(refs)==2
    assert {r['variant'] for r in refs}=={'full','small'}
    assert all(r['gallery_media_id']=='8' for r in refs)


def test_archive_body_hash_is_checked_before_url_inventory(tmp_path):
    body=b'<img alt="floor plan1">';sha=hashlib.sha256(body).hexdigest();p=tmp_path/sha[:2]/(sha+'.gz');p.parent.mkdir();p.write_bytes(gzip.compress(body))
    assert checked_body(tmp_path,sha)==body
    p.write_bytes(gzip.compress(b'changed'))
    with pytest.raises(ValueError,match='body hash mismatch'):checked_body(tmp_path,sha)
    with pytest.raises(ValueError,match='Invalid body hash'):checked_body(tmp_path,'../bad')
