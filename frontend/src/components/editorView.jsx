import { useState, useRef } from 'react';
import { useNavigate } from 'react-router-dom';
import ReactQuill from 'react-quill';
import 'react-quill/dist/quill.snow.css';
import { pdfExporter } from 'quill-to-pdf';
import { saveAs } from 'file-saver';
import { generateWord } from 'quill-to-word';
import Header from './Header';
import '../styles/editorView.css';

const EditorView = () => {
  const [content, setContent] = useState('');
  const [isDownloading, setIsDownloading] = useState(false);
  const [downloadMessage, setDownloadMessage] = useState('');
  const [exportFormat, setExportFormat] = useState('docx');
  const quillRef = useRef(null);
  const fileInputRef = useRef(null);
  const navigate = useNavigate();

  const modules = {
    toolbar: [
      [{ 'header': [1, 2, 3, false] }],
      ['bold', 'italic', 'underline', 'strike'],
      [{ 'list': 'ordered' }, { 'list': 'bullet' }],
      [{ 'indent': '-1' }, { 'indent': '+1' }],
      [{ 'align': [] }],
      [{ 'link': [] }],
      [{'color': [] }, { 'background': [] }],
      ['clean']
    ]
  };
  const formats = [
    'header',
    'bold', 'italic', 'underline', 'strike',
    'list', 'bullet',
    'indent',
    'link',
    'align',
    'color', 'background'
  ];

  const handleContentChange = (value) => {
    setContent(value);
  };

  const handleFormatChange = (e) => {
    setExportFormat(e.target.value);
  };

  const handleExport = async () => {
    if (!content.trim()) {
      setDownloadMessage('Cannot download empty content.');
      setTimeout(() => setDownloadMessage(''), 3000);
      return;
    }
    
    setIsDownloading(true);
    setDownloadMessage('');
    
    try {
      if (exportFormat === 'pdf') {
        await exportToPDF();
      } else if (exportFormat === 'docx') {
        await exportToDOCX();
      } else if (exportFormat === 'txt') {
        exportToTXT();
      }
      
      setDownloadMessage(`${exportFormat.toUpperCase()} downloaded successfully.`);
      setTimeout(() => {
        setDownloadMessage('');
      }, 3000);
    } catch (error) {
      console.error(`Error downloading ${exportFormat.toUpperCase()}:`, error);
      setDownloadMessage(`Error downloading ${exportFormat.toUpperCase()}. Please try again.`);
    } finally {
      setIsDownloading(false);
    }
  };

  const exportToPDF = async () => {
    const quillEditor = quillRef.current.getEditor();
    
    const pdfOptions = {
      filename: 'ESRS_Report.pdf',
      exportAs: 'blob',
      styleOptions: {
        paragraphSpacing: {
          before: 120,
          after: 240,
        },
        pageMargins: {
          top: 180,
          right: 180,
          bottom: 180,
          left: 180,
        },
      },
      title: 'ESRS Report',
      author: 'ESGenerator',
      subject: 'European Sustainability Reporting Standards',
      keywords: 'ESRS, Sustainability, Report',
      headerText: 'ESRS Report',
      footerText: `Generated on ${new Date().toLocaleDateString()}`,
    };
    
    const pdfBlob = await pdfExporter.generatePdf(quillEditor.getContents(), pdfOptions);
    
    if (window.showSaveFilePicker) {
      try {
        const opts = {
          suggestedName: 'ESRS_Report.pdf',
          types: [{
            description: 'PDF File',
            accept: {'application/pdf': ['.pdf']}
          }]
        };
        
        const fileHandle = await window.showSaveFilePicker(opts);
        const writable = await fileHandle.createWritable();
        await writable.write(pdfBlob);
        await writable.close();
      } catch (err) {
        if (err.name !== 'AbortError') {
          saveAs(pdfBlob, 'ESRS_Report.pdf');
        }
      }
    } else {
      saveAs(pdfBlob, 'ESRS_Report.pdf');
    }
  };

  const exportToDOCX = async () => {
    const quillEditor = quillRef.current.getEditor();
    
    const docxOptions = {
      exportAs: 'blob',
      styleOptions: {
        paragraphSpacing: {
          before: 120,
          after: 240,
        },
        pageMargins: {
          top: 360, 
          right: 360,
          bottom: 360,
          left: 360,
        },
      },
      
      title: 'ESRS Report',
      subject: 'European Sustainability Reporting Standards',
      creator: 'ESGenerator',
      description: 'ESRS Report generated with ESGenerator',
      lastModifiedBy: 'ESGenerator User',
    };
    
    const docxBlob = await generateWord(quillEditor.getContents(), docxOptions);
    if (window.showSaveFilePicker) {
      try {
        const opts = {
          suggestedName: 'ESRS_Report.docx',
          types: [{
            description: 'Word Document',
            accept: {'application/vnd.openxmlformats-officedocument.wordprocessingml.document': ['.docx']}
          }]
        };
        
        const fileHandle = await window.showSaveFilePicker(opts);
        const writable = await fileHandle.createWritable();
        await writable.write(docxBlob);
        await writable.close();
      } catch (err) {
        if (err.name !== 'AbortError') {
          saveAs(docxBlob, 'ESRS_Report.docx');
        }
      }
    } else {
      saveAs(docxBlob, 'ESRS_Report.docx');
    }
  };

  const exportToTXT = async () => {
    const quillEditor = quillRef.current.getEditor();
    const plainText = quillEditor.getText();
    const txtBlob = new Blob([plainText], { type: 'text/plain;charset=utf-8' });
    if (window.showSaveFilePicker) {
      try {
        const opts = {
          suggestedName: 'ESRS_Report.txt',
          types: [{
            description: 'Text File',
            accept: {'text/plain': ['.txt']}
          }]
        };
        
        const fileHandle = await window.showSaveFilePicker(opts);
        const writable = await fileHandle.createWritable();
        await writable.write(txtBlob);
        await writable.close();
      } catch (err) {
        if (err.name !== 'AbortError') {
          saveAs(txtBlob, 'ESRS_Report.txt');
        }
      }
    } else {
      saveAs(txtBlob, 'ESRS_Report.txt');
    }
  };

  return (
    <>
      <Header />
      <div className="main-content">
        <div className="container">
          <div className="nav-container">
            <button 
              className="nav-button inactive" 
              onClick={() => navigate('/')}
            >
              Chat
            </button>
            <button className="nav-button active">Editor</button>
          </div>
          
          <div className="editor-container">
            <div className="quill-wrapper">
              <ReactQuill
                ref={quillRef}
                theme="snow"
                value={content}
                onChange={handleContentChange}
                modules={modules}
                formats={formats}
                placeholder="Write your ESRS report here..."
              />
            </div>
            
            <div className="editor-controls">
              {downloadMessage && (
                <div className={`save-message ${downloadMessage.includes('Error') || downloadMessage.includes('Cannot') ? 'error' : 'success'}`}>
                  {downloadMessage}
                </div>
              )}
              
              <div className="export-options">
                <select 
                  className="format-selector" 
                  value={exportFormat} 
                  onChange={handleFormatChange}
                >
                  <option value="pdf">PDF</option>
                  <option value="docx">Word Document (.docx)</option>
                  <option value="txt">Plain Text (.txt)</option>
                </select>
                
                <button 
                  className="save-button"
                  onClick={handleExport}
                  disabled={isDownloading}
                >
                  {isDownloading ? `Preparing ${exportFormat.toUpperCase()}...` : `Download ${exportFormat.toUpperCase()}`}
                </button>
              </div>
            </div>
          </div>
        </div>
      </div>
    </>
  );
};

export default EditorView;