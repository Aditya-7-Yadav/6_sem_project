# OCR Frontend Application

A modern, production-ready frontend for document OCR (Optical Character Recognition) processing. Built with React, Vite, and TailwindCSS.

## Features

- 🎨 **Modern UI/UX**: Clean, minimalist design inspired by Notion, Stripe, and Linear
- 📤 **Drag & Drop Upload**: Intuitive file upload with drag-and-drop support
- 📊 **Real-time Progress**: Visual upload progress indicator
- 📄 **Result Viewer**: Clean, scrollable text viewer with copy-to-clipboard functionality
- 📱 **Responsive Design**: Fully responsive for desktop and mobile devices
- ⚡ **Fast & Lightweight**: Built with Vite for optimal performance
- 🎭 **Smooth Animations**: Subtle transitions and animations for premium feel

## Tech Stack

- **React 18** - UI library
- **Vite** - Build tool and dev server
- **TailwindCSS** - Utility-first CSS framework
- **React Router** - Client-side routing
- **Axios** - HTTP client for API calls

## Project Structure

```
frontend/
├── public/              # Static assets
├── src/
│   ├── components/      # Reusable components
│   │   ├── Header.jsx
│   │   ├── FileUpload.jsx
│   │   └── ResultViewer.jsx
│   ├── pages/          # Page components
│   │   ├── Login.jsx
│   │   └── Dashboard.jsx
│   ├── services/       # API services
│   │   └── api.js
│   ├── App.jsx         # Main app component
│   ├── main.jsx        # Entry point
│   └── index.css       # Global styles
├── .env                # Environment variables
├── index.html          # HTML template
├── package.json        # Dependencies
├── tailwind.config.js  # Tailwind configuration
├── vite.config.js      # Vite configuration
└── README.md           # This file
```

## Prerequisites

- Node.js 16+ and npm/yarn installed
- Backend API running on `http://localhost:3000` (or configured endpoint)

## Installation

1. **Navigate to the frontend directory:**
   ```bash
   cd frontend
   ```

2. **Install dependencies:**
   ```bash
   npm install
   ```

3. **Configure environment variables:**
   
   The `.env` file is already created. Update if your backend runs on a different URL:
   ```env
   VITE_API_URL=http://localhost:3000
   ```

## Running the Application

### Development Mode

Start the development server with hot reload:

```bash
npm run dev
```

The application will open automatically at `http://localhost:5173`

### Production Build

Build for production:

```bash
npm run build
```

Preview production build:

```bash
npm run preview
```

## Usage

1. **Login Page**
   - Enter any email and password (authentication is UI-only)
   - Click "Sign in" to navigate to the dashboard

2. **Dashboard**
   - Drag and drop a PDF file onto the upload area, or click to browse
   - Click "Process Document" to upload and process
   - View extracted text in the result viewer
   - Copy text to clipboard using the "Copy" button
   - Clear results and upload a new file using the reset button

## API Integration

The frontend expects the backend API to:

- **Endpoint**: `POST /run`
- **Request**: FormData with key `file` containing the PDF
- **Response**: JSON with format:
  ```json
  {
    "output": "extracted text here"
  }
  ```

Update the API URL in `.env` if your backend runs on a different port or host.

## Customization

### Colors

Edit [tailwind.config.js](tailwind.config.js#L7-L19) to change the color scheme:

```javascript
theme: {
  extend: {
    colors: {
      primary: {
        // Your custom colors
      }
    }
  }
}
```

### Components

All components are in [src/components/](src/components/) and can be customized:
- [Header.jsx](src/components/Header.jsx) - Navigation header
- [FileUpload.jsx](src/components/FileUpload.jsx) - Upload component
- [ResultViewer.jsx](src/components/ResultViewer.jsx) - Result display

### Pages

- [Login.jsx](src/pages/Login.jsx) - Authentication page
- [Dashboard.jsx](src/pages/Dashboard.jsx) - Main application page

## Browser Support

- Chrome/Edge 90+
- Firefox 88+
- Safari 14+

## Troubleshooting

**CORS errors:**
- Ensure your backend allows requests from `http://localhost:5173`
- Add CORS headers to your backend API

**API connection issues:**
- Verify backend is running on the correct port
- Check `.env` file has correct `VITE_API_URL`
- Restart dev server after changing `.env`

**Build errors:**
- Clear node_modules and reinstall: `rm -rf node_modules && npm install`
- Clear Vite cache: `rm -rf node_modules/.vite`

## License

MIT

## Contributing

1. Fork the repository
2. Create your feature branch (`git checkout -b feature/AmazingFeature`)
3. Commit your changes (`git commit -m 'Add some AmazingFeature'`)
4. Push to the branch (`git push origin feature/AmazingFeature`)
5. Open a Pull Request
