import fs from 'node:fs/promises';
import path from 'node:path';
import {pathToFileURL} from 'node:url';
import {Presentation, PresentationFile} from '@oai/artifact-tool';
const root='C:/Revelator/conceptual-model';
const skill='C:/Users/quert/.codex/plugins/cache/openai-primary-runtime/presentations/26.1015.12040/skills/presentations';
const p=Presentation.create({slideSize:{width:1280,height:720}});
const s=p.slides.add(); s.background.fill='#080F1B';
const white='#F1F5FA', muted='#B6C3D5', teal='#18D4D1';
function box(x,y,w,h,fill,geometry='rect'){return s.shapes.add({geometry,position:{left:x,top:y,width:w,height:h},fill,line:{fill:'none',width:0}});}
function text(txt,x,y,w,h,size=22,color=white,bold=false){const t=box(x,y,w,h,'none','textbox');t.text=txt;t.text.style={typeface:'Arial',fontSize:size,color,bold};return t;}
box(54,37,52,4,teal);
text('PROJECT FRAMEWORK',54,49,500,18,10,teal,true);
text('Conceptual Model of the Project',54,90,1100,52,34,white,true);
text('The resources, development stages, system output, and evaluation of Revelator.',54,150,1150,28,16,muted);
const panel=box(66,212,1148,410,'#17253B','roundRect'); panel.borderRadius='rounded-3xl';
const xs=[94,405,658,947];
const ws=[274,210,251,233];
['INPUT','PROCESS','OUTPUT','EVALUATION'].forEach((t,i)=>text(t,xs[i],240,ws[i],28,20,teal,true));
[386,638,926].forEach(x=>box(x,242,1,342,'#35455E'));
text('Knowledge',94,284,274,28,20,white,true);
text('Document forensics, 15 forgery\ncategories, prompt engineering,\nAPIs, development, and security',94,316,280,78,17,muted);
text('Software',94,402,274,26,20,white,true);
text('Python / FastAPI, SQLite,\nReact / Vite / PWA, Gemini API,\nand Cloudflare',94,434,280,74,17,muted);
text('Hardware',94,518,274,26,20,white,true);
text('Computer, internet, and\nserver with at least 4 GB RAM',94,550,280,52,17,muted);
['Requirements','Design','Development','Testing','Deployment','Review'].forEach((v,i)=>{
text(String(i+1),405,290+i*49,30,28,14,teal,true);
text(v,444,286+i*49,180,32,21,white);
});
text('REVELATOR',658,288,251,40,27,white,true);
text('AI-assisted document\nforgery analysis system\nusing Gemini Vision',658,338,251,100,21,white);
text('Web and Android application',658,452,251,48,18,teal);
text('Preliminary findings,\nexplanations, and scan history',658,520,251,72,18,muted);
text('SUS',947,290,233,34,27,white,true);
text('System Usability Scale',947,332,233,54,20,muted);
text('ISO/IEC 25010',947,434,233,34,25,white,true);
text('Software quality\nevaluation',947,478,233,76,20,muted);
text('REVELATOR • FINAL DEFENSE',54,682,600,16,9,muted);
text('LSPU – San Pablo City Campus',1000,682,240,16,9,muted);
text('04',1190,49,50,20,10,muted);
s.speakerNotes.text='Source: NEW COPY DOC.docx, Chapter I, Conceptual Model of the Project, and user-provided conceptual-model image. Input details are grouped for slide readability. Knowledge includes document forensics and the 15-category taxonomy, prompt engineering, Google GenAI integration, web development and RESTful APIs, SQLite/SQLAlchemy, JWT authentication, three-tier RBAC, mobile UI/UX, Python and FastAPI. Software includes Python 3.11+, FastAPI, Uvicorn, SQLAlchemy, SQLite, React, React Router, React Native, Vite, PWA, HTML, CSS, JavaScript, Visual Studio Code and Cloudflare. Hardware includes a computer or laptop, internet, and an implementation server with at least 4 GB RAM. Process: Requirements, Design, Development, Testing, Deployment, Review. Output full title: Revelator: An AI-Assisted Web and Mobile App Document Forgery Analysis System using Gemini Vision. Evaluation: System Usability Scale (SUS) and ISO/IEC 25010 Software Quality Evaluation.';
await fs.writeFile(root+'/output/Conceptual-Model.png',new Uint8Array(await (await p.export({slide:s,format:'png',scale:1.5})).arrayBuffer()));
const candidate=root+'/.build/candidate.pptx';
await (await PresentationFile.exportPptx(p)).save(candidate);
const {finalizePresentation}=await import(pathToFileURL(path.join(skill,'container_tools/artifact_tool_utils.mjs')).href);
const res=await finalizePresentation({workspaceDir:root,candidatePath:candidate,finalPath:root+'/output/Conceptual-Model-Editable.pptx',pythonExecutable:'C:/Users/quert/.cache/codex-runtimes/codex-primary-runtime/dependencies/python/python.exe',integrityValidatorPath:skill+'/container_tools/inspect_presentation_package_integrity.py',layoutValidatorPath:skill+'/container_tools/inspect_presentation_layout_geometry.py',layoutArgs:['--expected-slide-size-emu','12192000,6858000','--validate-bullet-geometry','--validate-heading-fit'],explicitTotalSlideCount:1,requiredNativeTableOwnerSlides:[],fontPolicy:{basis:'design',families:['Arial']},verifyArtifactToolImport:true,receiptPath:root+'/.build/validation-final.json'});
console.log(JSON.stringify(res));



