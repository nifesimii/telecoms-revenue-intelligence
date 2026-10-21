import fs from "node:fs/promises";
import { Presentation, PresentationFile } from "@oai/artifact-tool";

const OUT = "/Users/ademoyeoluwanifesimi/Documents/telecoms-revenue-intelligence/docs/FBB_Product_Demo_Executive_Review.pptx";
const RENDER = "/Users/ademoyeoluwanifesimi/Documents/telecoms-revenue-intelligence/.tmp/product_deck/rendered";
const SCREEN = "/Users/ademoyeoluwanifesimi/Documents/telecoms-revenue-intelligence/.tmp/product_deck/screens";
const W = 1280, H = 720;
const C = { ink:"#141414", muted:"#5F6368", line:"#D7D9DD", panel:"#F1F2F4", yellow:"#FFCC00", yellowSoft:"#FFF7C2", red:"#A51D24", green:"#137A4A", blue:"#1769AA", white:"#FFFFFF" };
const FONT = "Arial";

async function bytes(path){ const b=await fs.readFile(path); return b.buffer.slice(b.byteOffset,b.byteOffset+b.byteLength); }
function box(slide,x,y,w,h,fill=C.panel,line="none",radius="rect") { return slide.shapes.add({geometry:radius,position:{left:x,top:y,width:w,height:h},fill,line:{style:"solid",fill:line,width:line==="none"?0:1}}); }
function text(slide,txt,x,y,w,h,size=24,color=C.ink,bold=false,align="left") { const s=slide.shapes.add({geometry:"textbox",position:{left:x,top:y,width:w,height:h},fill:"none",line:{style:"solid",fill:"none",width:0}}); s.text=txt; s.text.style={fontFamily:FONT,fontSize:size,color,bold,alignment:align,verticalAlignment:"middle"}; return s; }
function label(slide,txt,x,y,w=260){ return text(slide,txt.toUpperCase(),x,y,w,24,13,C.muted,true); }
function title(slide,txt,kicker){ if(kicker) label(slide,kicker,72,44,450); text(slide,txt,72,75,1136,72,40,C.ink,true); box(slide,72,154,1136,2,C.line); }
function footer(slide,n){ text(slide,"FBB TRADE PARTNER INTELLIGENCE",72,684,380,18,11,C.muted,true); text(slide,String(n).padStart(2,"0"),1160,684,48,18,11,C.muted,true,"right"); }
async function image(slide,path,x,y,w,h){ slide.images.add({blob:await bytes(path),contentType:"image/png",alt:"Product interface screenshot",fit:"cover",position:{left:x,top:y,width:w,height:h}}); }
function note(slide,body){ slide.speakerNotes.textFrame.setText(body+"\n\n[Sources]\n- Repository: PROGRESS.md, ARCHITECTURE.md, docs/GM_DEMO.md\n- Product screenshots captured from localhost in sample-data mode on 2026-09-08\n[/Sources]"); }
function bullet(slide,head,body,y,color=C.ink){ text(slide,head,92,y,360,32,23,color,true); text(slide,body,470,y-2,670,56,19,C.muted,false); }

const p=Presentation.create({slideSize:{width:W,height:H}});

// 1
{
 const s=p.slides.add(); s.background.fill=C.white;
 box(s,0,0,20,H,C.yellow); label(s,"Executive product review",72,72,500);
 text(s,"FBB Trade Partner\nIntelligence",72,126,760,170,62,C.ink,true);
 text(s,"From commission questions to evidence-backed decisions",74,326,760,50,25,C.muted,false);
 box(s,74,426,430,74,C.ink); text(s,"PRODUCT DEMO",96,443,386,38,22,C.white,true);
 text(s,"Finance · Revenue Assurance · FBB Operations",74,614,700,30,16,C.muted,false);
 note(s,"Open with the decision: this is not another reporting dashboard. It is a finance investigation workflow that links what we owe, what was paid, why a variance exists, and the evidence behind the conclusion.");
}

// 2
{
 const s=p.slides.add(); title(s,"The cost is not calculating commission—it is proving it","Why this matters");
 text(s,"Finance teams can see numbers. The hard part is answering the next question with confidence:",72,185,1000,44,23,C.muted,false);
 bullet(s,"What do we owe?","Ranked dealer totals and denomination-level commission evidence.",263);
 bullet(s,"Why did it change?","Month-on-month movements explained against the documented business rules.",344);
 bullet(s,"Why was it zero?","Root-cause classification restricted to four approved causes—no speculation.",425);
 bullet(s,"Was it settled correctly?","Owed, paid, outstanding, disputes, and audit evidence in one investigation path.",506);
 footer(s,2); note(s,"Set up the pain before the product tour. Emphasize auditability and dispute turnaround—not only analytics.");
}

// 3
{
 const s=p.slides.add(); title(s,"One workflow now connects entitlement, settlement, and assurance","What we built");
 const xs=[72,315,558,801,1044], ws=[210,210,210,210,164];
 const heads=["Entitlement","Qualification","Inventory","Settlement","Evidence"];
 const bodies=["Commission + ORSC","Activation eligibility","Purchases vs activations","Paid vs owed","6-step audit trail"];
 for(let i=0;i<5;i++){ box(s,xs[i],230,ws[i],180,i===4?C.yellowSoft:C.panel,C.line); text(s,String(i+1).padStart(2,"0"),xs[i]+18,246,50,28,15,C.muted,true); text(s,heads[i],xs[i]+18,297,ws[i]-36,35,23,C.ink,true); text(s,bodies[i],xs[i]+18,348,ws[i]-36,58,17,C.muted,false); }
 text(s,"The same dealer-period can be followed end to end—without dynamic SQL or production write-back.",72,494,1040,64,27,C.ink,true);
 text(s,"Read-only data access · parameterized queries · documented rule boundaries",72,584,1040,32,17,C.muted,false);
 footer(s,3); note(s,"This is the product architecture in business language. The platform validates existing calculations; it does not replace the commission engine.");
}

// 4
{
 const s=p.slides.add(); title(s,"The overview turns a reporting month into a prioritized action list","Control tower");
 await image(s,`${SCREEN}/01-overview.png`,72,184,790,444);
 label(s,"March 2026 sample",902,194,300);
 text(s,"NGN 47.64m",902,240,300,54,36,C.ink,true);
 text(s,"commission owed",902,292,260,28,17,C.muted,false);
 text(s,"NGN 7.11m",902,349,300,54,36,C.red,true);
 text(s,"outstanding",902,401,260,28,17,C.muted,false);
 text(s,"35 dealers",902,458,300,54,36,C.ink,true);
 text(s,"flagged across multiple modules",902,510,285,50,17,C.muted,false);
 text(s,"Every headline links to the investigation surface that owns it.",902,584,280,48,18,C.ink,true);
 footer(s,4); note(s,"Live demo: start here. Point out the synthetic badge, Current Position, exceptions deep-link, audit coverage, and dealers appearing across modules.");
}

// 5
{
 const s=p.slides.add(); title(s,"Activation intelligence explains both volume and qualification","Activation assurance");
 await image(s,`${SCREEN}/03-activation.png`,72,205,755,405);
 text(s,"Summary",866,205,300,30,23,C.ink,true); text(s,"Qualified vs unqualified, rates, and expected commission.",866,242,310,62,17,C.muted,false);
 text(s,"Variance",866,322,300,30,23,C.ink,true); text(s,"Period-over-period movement by dealer for targeted follow-up.",866,359,310,62,17,C.muted,false);
 text(s,"Exceptions",866,439,300,30,23,C.ink,true); text(s,"All-unqualified, low-rate, zero-commission, and material drops.",866,476,310,62,17,C.muted,false);
 text(s,"Search persists across tabs; export matches the visible view.",866,570,310,45,17,C.ink,true);
 footer(s,5); note(s,"Live demo: show Summary, Variance, and Exceptions. Search for one dealer and export the current view.");
}

// 6
{
 const s=p.slides.add(); title(s,"Inventory checks distinguish leakage risk from missing evidence","Inventory assurance");
 await image(s,`${SCREEN}/04-inventory.png`,448,184,760,428);
 text(s,"Three outcomes",72,202,310,36,24,C.ink,true);
 text(s,"Confirmed mismatch",92,270,300,30,22,C.red,true); text(s,"Activations exceed invoiced purchases after supported checks.",92,306,300,56,17,C.muted,false);
 text(s,"No invoice record",92,382,300,30,22,C.blue,true); text(s,"A data-coverage gap—not automatically a mismatch.",92,418,300,56,17,C.muted,false);
 text(s,"Within allocation",92,494,300,30,22,C.green,true); text(s,"Available purchase evidence supports the activation volume.",92,530,300,56,17,C.muted,false);
 text(s,"Server-owned search, filtering, sorting, totals, and pagination keep the table bounded.",72,584,330,60,17,C.muted,false);
 footer(s,6); note(s,"Live demo: search Hynex to show the known SKU alias pattern. Expand Verify on a mismatch. Mention ServiceNow-ready data-coverage ticket drafting.");
}

// 7
{
 const s=p.slides.add(); title(s,"Payment intelligence closes the loop from owed to settled","Settlement assurance");
 await image(s,`${SCREEN}/05-payment.png`,72,184,760,428);
 text(s,"One bounded collection",866,202,320,36,24,C.ink,true);
 text(s,"Exceptions and All Payments are filtered views of the same source—avoiding duplicate reads and hidden rendering.",866,250,310,96,18,C.muted,false);
 text(s,"Dealer statement",866,382,320,36,24,C.ink,true);
 text(s,"Combines commission entitlement, payment settlement, ORSC context, position, and linked audit trails.",866,430,310,92,18,C.muted,false);
 text(s,"Exports: Markdown · CSV · XLSX · XLSB",866,557,320,42,17,C.ink,true);
 footer(s,7); note(s,"Live demo: Payment Intelligence → All Payments → Statement. Walk owed, settled, variance, position, linked trails, and export options. Then return to Exceptions and open a dispute draft.");
}

// 8
{
 const s=p.slides.add(); title(s,"The finance assistant turns a finding into a grounded explanation","Commission intelligence");
 await image(s,`${SCREEN}/02-commission.png`,530,184,678,428);
 text(s,"Ask in business language",72,203,410,36,25,C.ink,true);
 const qs=["Summarise dealer commissions for March","Why did this dealer change vs February?","Classify the zero-commission records","Show the ORSC summary for the period"];
 for(let i=0;i<qs.length;i++){ text(s,"“"+qs[i]+"”",88,263+i*76,390,55,18,i===1?C.red:C.ink,i===1); }
 box(s,72,586,410,2,C.yellow); text(s,"Answers identify the tools called and stay inside the knowledge base.",72,603,410,44,17,C.muted,false);
 footer(s,8); note(s,"Live demo only if the Anthropic key is healthy. Use a templated Ask Claude action from Overview or a row. Multi-tool responses may take 20–30 seconds.");
}

// 9
{
 const s=p.slides.add(); title(s,"Four audit modules make conclusions challengeable—not opaque","Verification chains");
 const rows=[
  ["Zero-Commission","Was a partner paid for zero-commission activity?","PAID · NOT_PAID · INSUFFICIENT_DATA"],
  ["Inventory Mismatch","Do activations exceed supported purchases?","RECONCILED · EXCESS_ACTIVATION · INSUFFICIENT_DATA"],
  ["Payment Reconciliation","Was the partner paid the correct amount?","PAID_IN_FULL · UNDERPAID · OVERPAID · ROUNDING"],
  ["Eligibility Window","Is the six-month rule truly the cause?","POLICY_MET · POLICY_VIOLATED · MIXED_ATTRIBUTION"]
 ];
 for(let i=0;i<4;i++){ const y=190+i*101; box(s,72,y,1136,82,i===2?C.yellowSoft:C.panel,C.line); text(s,rows[i][0],92,y+13,260,28,21,C.ink,true); text(s,rows[i][1],365,y+10,405,32,17,C.ink,false); text(s,rows[i][2],365,y+45,800,24,14,C.muted,true); }
 text(s,"Each persisted chain records what was checked, what was found, step-level caveats, and HIGH / MEDIUM / LOW confidence.",72,615,1100,44,20,C.ink,true);
 footer(s,9); note(s,"Audit Trails requires Postgres. In the local session Docker was not running, so use the hosted preview or start Docker before presenting. Pick Payment Reconciliation for the clearest business story.");
}

// 10
{
 const s=p.slides.add(); title(s,"The demo should follow one dealer from signal to evidence","Recommended live path");
 const steps=["Start with\nCurrent Position","Open a\npayment exception","Verify the\nactivation evidence","Open the\ndealer statement","Walk the\naudit chain"];
 for(let i=0;i<5;i++){ const x=72+i*226; text(s,String(i+1),x,220,54,54,36,i===4?C.red:C.ink,true); box(s,x,294,196,150,i===4?C.yellowSoft:C.panel,C.line); text(s,steps[i],x+18,319,160,96,22,C.ink,true); if(i<4) text(s,"→",x+195,340,30,40,28,C.muted,true,"center"); }
 text(s,"Close the story with the decision the evidence supports—not with a tour of every tab.",72,514,1000,52,28,C.ink,true);
 text(s,"Backup paths: activation exception · Hynex inventory pattern · dispute-response draft · CSV export",72,594,1080,32,17,C.muted,false);
 footer(s,10); note(s,"Use this sequence as the live-demo spine. Aim for 6–8 minutes, then use the deck for architecture, readiness, and the approval ask.");
}

// 11
{
 const s=p.slides.add(); title(s,"The MVP is demo-ready, bounded, and tested","Delivery confidence");
 const metrics=[["215","tests passing"],["28","live tests skipped by default"],["100","maximum rows per page"],["6","integrated product surfaces"]];
 for(let i=0;i<4;i++){ const x=72+i*284; text(s,metrics[i][0],x,211,230,70,48,i===0?C.green:C.ink,true); text(s,metrics[i][1],x,280,230,48,17,C.muted,false); }
 box(s,72,368,1136,2,C.line);
 bullet(s,"Safe by design","Read-only development sources, parameterized queries, no write-back, no dynamic SQL.",406);
 bullet(s,"Honest demo mode","Synthetic FBB and simulated payment data are visibly labelled and deterministic.",480);
 bullet(s,"Production foundation","Bounded APIs, server-side filtering, lazy verification evidence, request timing, and query caching.",554);
 footer(s,11); note(s,"State the boundary plainly: native Presto/Postgres pagination and real MTN data connections are follow-up work after production access and query plans are available.");
}

// 12
{
 const s=p.slides.add(); s.background.fill=C.ink; box(s,0,0,20,H,C.yellow); label(s,"Decision",72,74,300);
 text(s,"Approve the next validation step",72,130,920,70,48,C.white,true);
 text(s,"Move from a deterministic sample-data demo to a controlled pilot with Finance and Revenue Assurance.",72,224,960,72,27,"#D8DADD",false);
 const asks=["Confirm Finance-facing terminology and audit conclusions","Select the first real data integration and pilot period","Nominate users to validate dispute and dealer-statement workflows"];
 for(let i=0;i<3;i++){ text(s,String(i+1).padStart(2,"0"),72,366+i*72,54,34,18,C.yellow,true); text(s,asks[i],142,360+i*72,860,46,22,C.white,true); }
 text(s,"The platform already demonstrates the control model. Approval unlocks validation on governed real data.",72,620,1060,40,18,"#D8DADD",false);
 note(s,"End with a specific approval request. Ask for a controlled pilot—not blanket production deployment.");
}

await fs.mkdir(RENDER,{recursive:true});
for (const [i,s] of p.slides.items.entries()) {
 const blob=await p.export({slide:s,format:"png",scale:1});
 await fs.writeFile(`${RENDER}/slide-${String(i+1).padStart(2,"0")}.png`,new Uint8Array(await blob.arrayBuffer()));
}
const pptx=await PresentationFile.exportPptx(p); await pptx.save(OUT);
console.log(OUT);
