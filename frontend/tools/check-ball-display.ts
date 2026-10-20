import assert from 'node:assert/strict';
import {ballDisplay} from '../src/ballDisplay.ts';
for(const width of [320,600,1200,1920]) {
 const ground=ballDisplay(width,.135,true);
 assert.equal(ground.center,.135*ground.scale);
 assert.equal(ballDisplay(width,0,true).center,ground.center);
 assert.ok(ground.scale>=1.8&&ground.scale<=2.4);
 assert.ok(Math.abs(ballDisplay(width,2.135,true).center-ground.center-2)<1e-10);
 assert.equal(ballDisplay(width,.2,false).clearance,.2);
}
console.log('PASS tracking ground contact, bounded sizing, aerial height and synthetic clearance');
