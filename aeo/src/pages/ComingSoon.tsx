export default function ComingSoon({ title }: { title: string }) {
    return (
        <div className="panel__container">
            <h2 className="title">{title}</h2>
            <p>This section is coming soon.</p>
        </div>
    );
}
