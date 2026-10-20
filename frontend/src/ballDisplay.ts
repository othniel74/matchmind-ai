/** Tracking z is center height; synthetic z is ground clearance. */
export function ballDisplay(width:number,height:number,tracking:boolean) {
 const scale=tracking?Math.min(2.4,Math.max(1.8,1.8*900/Math.max(width,1))):3.3*Math.max(1,1200/Math.max(width,1));
 const clearance=Math.max(0,height-(tracking?.135:0));
 return {scale,clearance,center:.135*scale+clearance};
}
