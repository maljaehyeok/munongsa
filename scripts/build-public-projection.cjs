/* Build HTTP artifacts using the same existing field approval/basis filters as UI.
 * Inputs stay untouched. Run again when an approved source asset is released. */
const fs=require('node:fs'),vm=require('node:vm'),path=require('node:path'),assert=require('node:assert/strict');
const [feedPath,detailsPath,reviewPath,output,installedPolicy]=process.argv.slice(2);
assert.ok(output&&path.resolve(output)!==path.dirname(path.resolve(detailsPath)),'separate output directory required');
const root=path.resolve(__dirname,'..'),ctx=vm.createContext({URL});
for(const file of ['support-details','support-review'])vm.runInContext(fs.readFileSync(path.join(installedPolicy||path.join(root,'assets'),file+'.js'),'utf8'),ctx);
const feed=JSON.parse(fs.readFileSync(feedPath)),details=JSON.parse(fs.readFileSync(detailsPath)),review=JSON.parse(fs.readFileSync(reviewPath));
assert.equal(feed.schema_version,'munongsa-support-public-v1');assert.equal(details.schema,'munongsa-support-details-v1');assert.equal(details.preview,false);
ctx.MunongsaSupportDetails.install(details);
const records=[],withheld=[],links=[];
for(const item of feed.notices){
 if(item.rights?.public_display!=='allowed'||item.local_review_only)continue;
 const row=ctx.MunongsaSupportDetails.get(item);
 if(row)records.push(row);
 else if(details.records.some(r=>r.basis?.id===item.id))withheld.push(item.id);
 const link=ctx.MunongsaSupportDetails.linkHistory(item);
 if(link){const out={};for(const k of ['schema','basis','state','checked_at','expires_at'])out[k]=link[k];const application=ctx.MunongsaSupportDetails.application(item);if(application)out.application=application;links.push(out);}
}
// Existing public reference policy allows only curated official RSS metadata.
// No internal origin/summary/target fields are copied into the HTTP artifact.
const reviews=ctx.MunongsaSupportReview.publicRecords(review).map(r=>Object.fromEntries(Object.entries(r).filter(([k])=>['id','title','institution','url','published_at','checked_at','publication','recommendation_eligible','verification_status','record_type'].includes(k))));
fs.mkdirSync(output,{recursive:true});
fs.writeFileSync(path.join(output,'support-details.json'),JSON.stringify({schema:details.schema,preview:false,records,withheld_ids:withheld,link_reviews:links},null,2)+'\n');
fs.writeFileSync(path.join(output,'support-review.json'),JSON.stringify({schema_version:'munongsa-support-review-v1',records:reviews},null,2)+'\n');
console.log(JSON.stringify({source_details:details.records.length,public_details:records.length,withheld:withheld.length,source_reviews:review.records.length,public_reviews:reviews.length,links:links.length}));
