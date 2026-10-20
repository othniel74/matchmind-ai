import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import {sampleTracking,metricaSummary} from '../src/trackingData.ts';
const frames=JSON.parse(readFileSync('public/tracking/source-clip.json','utf8'));
const match=JSON.parse(readFileSync('public/tracking/source-match.json','utf8'));
assert.equal(frames.length,1201);
for(let i=0;i<frames.length;i++){
 assert.equal(frames[i].frame,2510+i);
 const pitch=sampleTracking(frames,match,i/10);
 assert.equal(pitch.players.length,frames[i].player_data.length);
 assert.equal(pitch.players.filter(p=>p.goalkeeper).length,pitch.players.length?2:0);
 assert.equal(new Set(pitch.players.map(p=>p.player_id)).size,pitch.players.length);
 for(const p of pitch.players){assert.ok(Number.isFinite(p.x)&&Number.isFinite(p.y));const raw=frames[i].player_data.find(q=>String(q.player_id)===p.player_id);assert.ok(Math.abs((p.x-50)*match.pitch_length/100-raw.x)<1e-9)}
 if(pitch.ballVisible) assert.ok(Math.abs((pitch.ball.x-50)*match.pitch_length/100-frames[i].ball_data.x)<1e-8);
}
const middle=sampleTracking(frames,match,.05);
assert.ok(Math.abs(middle.players[0].x-(sampleTracking(frames,match,0).players[0].x+sampleTracking(frames,match,.1).players[0].x)/2)<1e-9);
const missing=structuredClone(frames.slice(0,2));missing[0].ball_data.x=null;
assert.equal(sampleTracking(missing,match,0).ballVisible,false);
assert.deepEqual(sampleTracking(frames,match,0),sampleTracking(frames,match,-10));
assert.deepEqual(sampleTracking(frames,match,120),sampleTracking(frames,match,1000));
console.log('PASS 1,201 frames: roster, keeper identities, exact source-coordinate mapping, ball mapping, interpolation, missing-ball visibility, seek bounds');

const mf=JSON.parse(readFileSync('../backend/data/research/metrica/frames.json','utf8'));
const mm=JSON.parse(readFileSync('../backend/data/research/metrica/match.json','utf8'));
assert.equal(mm.fps,25);assert.equal(mf.length,3001);
for(let i=0;i<mf.length;i++){
 const pitch=sampleTracking(mf,mm,i/25);
 assert.equal(pitch.players.length,22);
 for(const p of pitch.players){const raw=mf[i].player_data.find(q=>String(q.player_id)===p.player_id);assert.ok(Math.abs((p.x-50)*105/100-raw.x)<1e-8)}
}
const half=sampleTracking(mf,mm,.02);
assert.ok(Math.abs(half.players[0].x-(sampleTracking(mf,mm,0).players[0].x+sampleTracking(mf,mm,.04).players[0].x)/2)<1e-9);
console.log('PASS Metrica: 3,001 frames, 25 Hz mapping and half-frame interpolation');

const me=JSON.parse(readFileSync('../backend/data/research/metrica/events.json','utf8'));
const shot=me.find(e=>e.type==='SHOT');
assert.equal(metricaSummary(me,shot.time)[0].goals,0);
assert.equal(metricaSummary(me,(shot.end_frame-1)/25)[0].goals,1);
assert.equal(metricaSummary(me,120)[1].goals,0);
console.log('PASS Metrica goal becomes known at the source shot end frame, not before');
